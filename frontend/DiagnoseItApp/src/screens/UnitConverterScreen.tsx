import React, { useEffect, useMemo, useState } from 'react';
import { View, StyleSheet, ScrollView, Alert } from 'react-native';
import {
  Text,
  TextInput,
  Button,
  Card,
  Title,
  Paragraph,
  Chip,
  ActivityIndicator,
  Menu,
} from 'react-native-paper';
import { SafeAreaView } from 'react-native-safe-area-context';
import type { LabTestType, LabTestValidationResult, UnitConversionResult } from '../services/api';
import { apiService } from '../services/api';
import { theme } from '../theme/theme';
import { getLabStatusColor } from '../utils/colors';

export default function UnitConverterScreen() {
  const [categories, setCategories] = useState<string[]>([]);
  const [category, setCategory] = useState('');
  const [tests, setTests] = useState<LabTestType[]>([]);
  const [units, setUnits] = useState<{ name: string; display_name: string }[]>([]);
  const [loadingTests, setLoadingTests] = useState(true);
  const [loadingUnits, setLoadingUnits] = useState(false);
  const [converting, setConverting] = useState(false);

  const [search, setSearch] = useState('');
  const [testName, setTestName] = useState('');
  const [fromUnit, setFromUnit] = useState('');
  const [toUnit, setToUnit] = useState('');
  const [value, setValue] = useState('');

  const [testMenuOpen, setTestMenuOpen] = useState(false);
  const [fromMenuOpen, setFromMenuOpen] = useState(false);
  const [toMenuOpen, setToMenuOpen] = useState(false);

  const [result, setResult] = useState<UnitConversionResult | null>(null);
  const [validation, setValidation] = useState<LabTestValidationResult | null>(null);

  useEffect(() => {
    apiService.getLabTestCategories()
      .then(cats => {
        setCategories(cats);
        if (cats.length > 0) setCategory(cats[0]);
      })
      .catch(() => Alert.alert('Error', 'Failed to load categories'))
      .finally(() => setLoadingTests(false));
  }, []);

  useEffect(() => {
    if (!category) return;
    setLoadingTests(true);
    setTestName('');
    setUnits([]);
    setResult(null);
    setValidation(null);
    apiService.getAllLabTestTypes(category)
      .then(setTests)
      .catch(() => Alert.alert('Error', 'Failed to load tests'))
      .finally(() => setLoadingTests(false));
  }, [category]);

  useEffect(() => {
    if (!testName) {
      setUnits([]);
      setFromUnit('');
      setToUnit('');
      return;
    }
    setLoadingUnits(true);
    setResult(null);
    setValidation(null);
    apiService.getLabTestUnits(testName)
      .then(data => {
        const opts = data.map(u => u.unit);
        setUnits(opts);
        const test = tests.find(t => t.name === testName);
        const defaultUnit = test?.default_unit || opts[0]?.name || '';
        setFromUnit(defaultUnit);
        const alt = opts.find(u => u.name !== defaultUnit);
        setToUnit(alt?.name || defaultUnit);
      })
      .catch(() => Alert.alert('Error', 'Failed to load units'))
      .finally(() => setLoadingUnits(false));
  }, [testName, tests]);

  const filteredTests = useMemo(() => {
    if (!search.trim()) return tests;
    const q = search.toLowerCase();
    return tests.filter(t =>
      t.display_name.toLowerCase().includes(q) ||
      t.name.toLowerCase().includes(q) ||
      t.aliases?.some(a => a.toLowerCase().includes(q))
    );
  }, [tests, search]);

  const selectedTest = tests.find(t => t.name === testName);
  const selectedTestLabel = selectedTest?.display_name || 'Select test';

  const handleConvert = async () => {
    if (!testName || !fromUnit || !toUnit || !value.trim()) {
      Alert.alert('Missing fields', 'Select a test, units, and enter a value');
      return;
    }
    if (fromUnit === toUnit) {
      Alert.alert('Invalid units', 'Choose different source and target units');
      return;
    }

    setConverting(true);
    setResult(null);
    setValidation(null);
    try {
      const converted = await apiService.convertLabUnits({
        test_type: testName,
        value: value.trim(),
        from_unit: fromUnit,
        to_unit: toUnit,
      });
      setResult(converted);
      try {
        const v = await apiService.validateLabTestValue({
          test_type: testName,
          value: String(converted.converted_value),
          unit: toUnit,
        });
        setValidation(v);
      } catch {
        /* optional */
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message.replace(/^API Error: \d+ \w+ - /, '') : 'Conversion failed';
      Alert.alert('Error', msg);
    } finally {
      setConverting(false);
    }
  };

  const swapUnits = () => {
    setFromUnit(toUnit);
    setToUnit(fromUnit);
    setResult(null);
    setValidation(null);
  };

  if (loadingTests && categories.length === 0) {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.centered}>
          <ActivityIndicator size="large" color={theme.colors.primary} />
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView contentContainerStyle={styles.content}>
        <Title style={styles.title}>Unit Converter</Title>
        <Paragraph style={styles.subtitle}>Convert lab values between units</Paragraph>

        <View style={styles.chipRow}>
          {categories.map(c => (
            <Chip
              key={c}
              selected={category === c}
              onPress={() => setCategory(c)}
              style={styles.chip}
              compact
            >
              {c}
            </Chip>
          ))}
        </View>

        <TextInput
          label="Search tests"
          value={search}
          onChangeText={setSearch}
          mode="outlined"
          style={styles.input}
        />

        <Menu
          visible={testMenuOpen}
          onDismiss={() => setTestMenuOpen(false)}
          anchor={
            <Button mode="outlined" onPress={() => setTestMenuOpen(true)} style={styles.input}>
              {selectedTestLabel}
            </Button>
          }
        >
          {filteredTests.map(t => (
            <Menu.Item
              key={t.name}
              onPress={() => { setTestName(t.name); setTestMenuOpen(false); }}
              title={t.display_name}
            />
          ))}
        </Menu>

        {selectedTest && (selectedTest.normal_min || selectedTest.normal_max) && (
          <Paragraph style={styles.hint}>
            Typical range: {selectedTest.normal_min ?? '—'} – {selectedTest.normal_max ?? '—'} {selectedTest.default_unit || ''}
          </Paragraph>
        )}

        <View style={styles.unitRow}>
          <Menu
            visible={fromMenuOpen}
            onDismiss={() => setFromMenuOpen(false)}
            anchor={
              <Button mode="outlined" onPress={() => setFromMenuOpen(true)} disabled={loadingUnits} style={styles.unitBtn}>
                From: {fromUnit || '—'}
              </Button>
            }
          >
            {units.map(u => (
              <Menu.Item key={u.name} onPress={() => { setFromUnit(u.name); setFromMenuOpen(false); }} title={u.display_name || u.name} />
            ))}
          </Menu>
          <Button mode="text" onPress={swapUnits} disabled={!fromUnit || !toUnit}>Swap</Button>
          <Menu
            visible={toMenuOpen}
            onDismiss={() => setToMenuOpen(false)}
            anchor={
              <Button mode="outlined" onPress={() => setToMenuOpen(true)} disabled={loadingUnits} style={styles.unitBtn}>
                To: {toUnit || '—'}
              </Button>
            }
          >
            {units.map(u => (
              <Menu.Item key={u.name} onPress={() => { setToUnit(u.name); setToMenuOpen(false); }} title={u.display_name || u.name} />
            ))}
          </Menu>
        </View>

        <TextInput
          label="Value"
          value={value}
          onChangeText={setValue}
          keyboardType="decimal-pad"
          mode="outlined"
          style={styles.input}
        />

        <Button mode="contained" onPress={handleConvert} loading={converting} disabled={converting || !testName}>
          Convert
        </Button>

        {result && (
          <Card style={styles.resultCard}>
            <Card.Content>
              <Title>Converted value</Title>
              <Text style={styles.resultValue}>
                {result.converted_value} {result.converted_unit}
              </Text>
              <Paragraph style={styles.formula}>
                {result.original_value} {result.original_unit} → {result.converted_value} {result.converted_unit}
              </Paragraph>
              <Paragraph>{result.formula}</Paragraph>
            </Card.Content>
          </Card>
        )}

        {validation && (
          <Card style={styles.resultCard}>
            <Card.Content>
              <Title>Reference check</Title>
              <Chip style={{ backgroundColor: getLabStatusColor(validation.status), alignSelf: 'flex-start', marginTop: 8 }}>
                <Text style={{ color: '#fff' }}>{validation.status}</Text>
              </Chip>
              <Paragraph style={{ marginTop: 8 }}>{validation.message}</Paragraph>
              {validation.normal_range && (
                <Paragraph style={styles.hint}>Normal: {validation.normal_range}</Paragraph>
              )}
            </Card.Content>
          </Card>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: theme.colors.background },
  content: { padding: 16, paddingBottom: 32 },
  centered: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  title: { fontSize: 24, fontWeight: 'bold' },
  subtitle: { color: theme.colors.onSurfaceVariant, marginBottom: 16 },
  chipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 12 },
  chip: { marginBottom: 4 },
  input: { marginBottom: 12 },
  hint: { fontSize: 12, color: theme.colors.onSurfaceVariant, marginBottom: 12 },
  unitRow: { flexDirection: 'row', alignItems: 'center', gap: 4, marginBottom: 12, flexWrap: 'wrap' },
  unitBtn: { flex: 1, minWidth: 120 },
  resultCard: { marginTop: 16, elevation: 2 },
  resultValue: { fontSize: 28, fontWeight: '700', color: theme.colors.primary, marginVertical: 8 },
  formula: { color: theme.colors.onSurfaceVariant, marginBottom: 4 },
});
