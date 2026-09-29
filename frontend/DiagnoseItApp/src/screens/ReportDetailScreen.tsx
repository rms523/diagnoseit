import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  View,
  StyleSheet,
  ScrollView,
  RefreshControl,
  Alert,
  Linking,
  Share,
} from 'react-native';
import {
  Text,
  Card,
  Title,
  Paragraph,
  Button,
  Chip,
  Divider,
  ActivityIndicator,
  TextInput,
  IconButton,
  Menu,
} from 'react-native-paper';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import type { LabTestTypeUnit, MedicalReport, TestResult } from '../services/api';
import { apiService, mediaUrl } from '../services/api';
import { theme } from '../theme/theme';
import { isReportParsing, statusLabel, testResultColor } from '../utils/reportStatus';

export default function ReportDetailScreen({ route, navigation }: any) {
  const { reportId } = route.params;
  const [report, setReport] = useState<MedicalReport | null>(null);
  const [testResults, setTestResults] = useState<TestResult[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const [editingId, setEditingId] = useState<number | null>(null);
  const [editForm, setEditForm] = useState({ value: '', unit: '', reference_range: '' });
  const [editUnits, setEditUnits] = useState<LabTestTypeUnit[]>([]);
  const [unitMenuFor, setUnitMenuFor] = useState<number | null>(null);
  const [convertMenuFor, setConvertMenuFor] = useState<number | null>(null);
  const [convertUnits, setConvertUnits] = useState<string[]>([]);
  const [convertingId, setConvertingId] = useState<number | null>(null);
  const [savingId, setSavingId] = useState<number | null>(null);

  const notifiedRef = useRef(false);

  const loadReport = useCallback(async (silent = false) => {
    try {
      if (!silent) setIsLoading(true);
      const data = await apiService.getMedicalReport(reportId);
      setReport(data);
      setTestResults(data.test_results ?? []);
    } catch {
      if (!silent) Alert.alert('Error', 'Failed to load medical report');
      setReport(null);
    } finally {
      if (!silent) setIsLoading(false);
    }
  }, [reportId]);

  useEffect(() => {
    loadReport();
    notifiedRef.current = false;
  }, [loadReport]);

  useEffect(() => {
    if (!report || !isReportParsing(report.status)) return;

    const id = setInterval(async () => {
      try {
        const status = await apiService.getReportStatus(reportId);
        if (status.status === 'COMPLETED' || status.status === 'FAILED') {
          await loadReport(true);
          if (!notifiedRef.current) {
            notifiedRef.current = true;
            Alert.alert(
              status.status === 'COMPLETED' ? 'Parsing complete' : 'Parsing failed',
              status.status === 'COMPLETED'
                ? 'Test results are ready.'
                : status.parse_error || 'Could not extract results from this report.',
            );
          }
        } else {
          setReport(prev => prev ? { ...prev, status: status.status } : prev);
        }
      } catch {
        /* ignore transient poll errors */
      }
    }, 5000);

    return () => clearInterval(id);
  }, [report?.status, reportId, loadReport]);

  const onRefresh = async () => {
    setRefreshing(true);
    await loadReport(true);
    setRefreshing(false);
  };

  const loadUnitsForTest = async (testName: string) => {
    try {
      setEditUnits(await apiService.getLabTestUnits(testName));
    } catch {
      setEditUnits([]);
    }
  };

  const startEdit = (result: TestResult) => {
    setEditingId(result.id);
    setEditForm({
      value: result.value,
      unit: result.unit,
      reference_range: result.reference_range,
    });
    loadUnitsForTest(result.test_type_name || result.test_name);
  };

  const cancelEdit = () => {
    setEditingId(null);
    setEditForm({ value: '', unit: '', reference_range: '' });
    setEditUnits([]);
    setUnitMenuFor(null);
  };

  const saveEdit = async (resultId: number) => {
    setSavingId(resultId);
    try {
      const updated = await apiService.updateTestResult(resultId, editForm);
      setTestResults(prev => prev.map(r => (r.id === resultId ? { ...r, ...updated } : r)));
      cancelEdit();
      Alert.alert('Saved', 'Test result updated');
    } catch (err) {
      const msg = err instanceof Error ? err.message.replace(/^API Error: \d+ \w+ - /, '') : 'Update failed';
      Alert.alert('Error', msg);
    } finally {
      setSavingId(null);
    }
  };

  const convertUnit = async (result: TestResult, targetUnit: string) => {
    setConvertingId(result.id);
    setConvertMenuFor(null);
    try {
      const converted = await apiService.convertTestResultUnit(result.id, targetUnit);
      setTestResults(prev =>
        prev.map(r =>
          r.id === result.id ? { ...r, value: converted.value, unit: converted.unit } : r
        )
      );
      Alert.alert('Converted', `Value converted to ${targetUnit}`);
    } catch (err) {
      const msg = err instanceof Error ? err.message.replace(/^API Error: \d+ \w+ - /, '') : 'Conversion failed';
      Alert.alert('Error', msg);
    } finally {
      setConvertingId(null);
    }
  };

  const validateResult = async (resultId: number) => {
    try {
      const result = await apiService.validateTestResult(resultId);
      setTestResults(prev =>
        prev.map(r => (r.id === resultId ? { ...r, status: result.status as TestResult['status'] } : r))
      );
      Alert.alert('Validation', `Status: ${result.status}`);
    } catch {
      Alert.alert('Error', 'Failed to validate result');
    }
  };

  const exportCSV = async () => {
    if (!report || testResults.length === 0) {
      Alert.alert('Nothing to export', 'No test results available');
      return;
    }
    const headers = 'Test Name,Value,Unit,Reference Range,Status';
    const rows = testResults.map(tr =>
      `"${tr.test_name}",${tr.value},"${tr.unit}","${tr.reference_range}",${tr.status}`
    );
    const csv = [headers, ...rows].join('\n');
    try {
      await Share.share({
        message: csv,
        title: `${report.title} results`,
      });
    } catch {
      Alert.alert('Error', 'Could not share CSV');
    }
  };

  const openFile = async () => {
    if (report?.file) {
      try {
        await Linking.openURL(mediaUrl(report.file));
      } catch {
        Alert.alert('Error', 'Could not open file');
      }
    }
  };

  const openConvertMenu = async (result: TestResult) => {
    try {
      const units = await apiService.getLabTestUnits(result.test_type_name || result.test_name);
      const alts = units.map(u => u.unit.name).filter(n => n && n !== result.unit);
      if (alts.length === 0) {
        Alert.alert('No conversion', 'No alternate units available for this test');
        return;
      }
      setConvertUnits(alts);
      setConvertMenuFor(result.id);
    } catch {
      Alert.alert('Error', 'Could not load units for this test');
    }
  };

  const renderResultCard = (result: TestResult) => {
    const isEditing = editingId === result.id;

    return (
      <Card key={result.id} style={styles.resultCard}>
        <Card.Content>
          <View style={styles.resultHeader}>
            <Text style={styles.testName}>{result.test_name}</Text>
            <Chip
              compact
              style={{ backgroundColor: testResultColor(result.status) }}
              textStyle={styles.chipText}
            >
              {result.status}
            </Chip>
          </View>

          {isEditing ? (
            <>
              <TextInput
                label="Value"
                value={editForm.value}
                onChangeText={v => setEditForm(prev => ({ ...prev, value: v }))}
                mode="outlined"
                dense
                style={styles.input}
              />
              <Menu
                visible={unitMenuFor === result.id}
                onDismiss={() => setUnitMenuFor(null)}
                anchor={
                  <Button mode="outlined" onPress={() => setUnitMenuFor(result.id)} style={styles.input}>
                    Unit: {editForm.unit || 'Select'}
                  </Button>
                }
              >
                {[editForm.unit, ...editUnits.map(u => u.unit.name)]
                  .filter((v, i, a) => v && a.indexOf(v) === i)
                  .map(name => (
                    <Menu.Item
                      key={name}
                      onPress={() => {
                        setEditForm(prev => ({ ...prev, unit: name }));
                        setUnitMenuFor(null);
                      }}
                      title={name}
                    />
                  ))}
              </Menu>
              <TextInput
                label="Reference range"
                value={editForm.reference_range}
                onChangeText={v => setEditForm(prev => ({ ...prev, reference_range: v }))}
                mode="outlined"
                dense
                style={styles.input}
              />
              <View style={styles.actionRow}>
                <Button
                  mode="contained"
                  compact
                  loading={savingId === result.id}
                  onPress={() => saveEdit(result.id)}
                >
                  Save
                </Button>
                <Button mode="text" compact onPress={cancelEdit}>Cancel</Button>
              </View>
            </>
          ) : (
            <>
              <Text style={styles.resultValue}>
                {result.value} <Text style={styles.resultUnit}>{result.unit}</Text>
              </Text>
              {result.reference_range ? (
                <Text style={styles.refRange}>Ref: {result.reference_range}</Text>
              ) : null}

              <View style={styles.actionRow}>
                <Button mode="outlined" compact onPress={() => startEdit(result)}>Edit</Button>
                <Button mode="outlined" compact onPress={() => validateResult(result.id)}>Validate</Button>
                <Menu
                  visible={convertMenuFor === result.id}
                  onDismiss={() => setConvertMenuFor(null)}
                  anchor={
                    <Button
                      mode="outlined"
                      compact
                      loading={convertingId === result.id}
                      onPress={() => openConvertMenu(result)}
                    >
                      Convert
                    </Button>
                  }
                >
                  {convertUnits.map(unit => (
                    <Menu.Item
                      key={unit}
                      onPress={() => convertUnit(result, unit)}
                      title={unit}
                    />
                  ))}
                </Menu>
              </View>
            </>
          )}
        </Card.Content>
      </Card>
    );
  };

  const renderTestResults = () => {
    if (report && isReportParsing(report.status) && testResults.length === 0) {
      return (
        <Card style={styles.card}>
          <Card.Content style={styles.centeredBlock}>
            <ActivityIndicator size="large" color={theme.colors.primary} />
            <Paragraph style={{ marginTop: 12, textAlign: 'center' }}>
              Parsing report — results will appear when complete.
            </Paragraph>
            <Text style={styles.hint}>Status updates every 5 seconds</Text>
          </Card.Content>
        </Card>
      );
    }

    if (report?.status === 'FAILED' && testResults.length === 0) {
      return (
        <Card style={styles.card}>
          <Card.Content>
            <Title>Parse failed</Title>
            <Paragraph style={{ color: theme.colors.error, marginTop: 8 }}>
              {report.parse_error || 'Could not extract test results from this report.'}
            </Paragraph>
          </Card.Content>
        </Card>
      );
    }

    if (testResults.length === 0) {
      return (
        <Card style={styles.card}>
          <Card.Content>
            <Title>Test results</Title>
            <Paragraph style={styles.noDataText}>No test results available.</Paragraph>
          </Card.Content>
        </Card>
      );
    }

    return (
      <View style={styles.resultsSection}>
        <View style={styles.resultsHeader}>
          <Title>Test results ({testResults.length})</Title>
          <Button mode="text" compact onPress={exportCSV}>Export CSV</Button>
        </View>
        <Paragraph style={styles.hint}>Tap Edit to correct values or units</Paragraph>
        {testResults.map(renderResultCard)}
      </View>
    );
  };

  if (isLoading) {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color={theme.colors.primary} />
          <Text style={styles.loadingText}>Loading report…</Text>
        </View>
      </SafeAreaView>
    );
  }

  if (!report) {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.errorContainer}>
          <Ionicons name="alert-circle" size={64} color={theme.colors.error} />
          <Title>Report not found</Title>
          <Button mode="contained" onPress={() => navigation.goBack()} style={styles.errorButton}>
            Go back
          </Button>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.topBar}>
        <IconButton icon="arrow-left" onPress={() => navigation.goBack()} />
        <Text style={styles.topTitle} numberOfLines={1}>{report.title}</Text>
      </View>

      <ScrollView
        style={styles.scrollView}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
      >
        <Card style={styles.headerCard}>
          <Card.Content>
            <View style={styles.headerActions}>
              {report.file && (
                <Button mode="outlined" onPress={openFile} icon="download" compact>
                  View file
                </Button>
              )}
              <Chip compact style={styles.parseChip}>
                {statusLabel(report.status, report.is_parsed)}
              </Chip>
            </View>

            <Divider style={styles.divider} />

            <View style={styles.detailsGrid}>
              <View style={styles.detailItem}>
                <Text style={styles.detailLabel}>Lab</Text>
                <Text style={styles.detailValue}>{report.lab_name || 'Unknown'}</Text>
              </View>
              <View style={styles.detailItem}>
                <Text style={styles.detailLabel}>Report date</Text>
                <Text style={styles.detailValue}>
                  {new Date(`${report.report_date}T00:00:00`).toLocaleDateString()}
                </Text>
              </View>
              <View style={styles.detailItem}>
                <Text style={styles.detailLabel}>Type</Text>
                <Text style={styles.detailValue}>{report.report_type}</Text>
              </View>
              <View style={styles.detailItem}>
                <Text style={styles.detailLabel}>Uploaded</Text>
                <Text style={styles.detailValue}>
                  {new Date(report.created_at).toLocaleDateString()}
                </Text>
              </View>
            </View>

            {report.parse_error && (
              <Paragraph style={{ color: theme.colors.error, marginTop: 12 }}>
                {report.parse_error}
              </Paragraph>
            )}
          </Card.Content>
        </Card>

        {renderTestResults()}

        {report.notes ? (
          <Card style={styles.card}>
            <Card.Content>
              <Title>Notes</Title>
              <Paragraph>{report.notes}</Paragraph>
            </Card.Content>
          </Card>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: theme.colors.background },
  topBar: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingRight: 12,
  },
  topTitle: { flex: 1, fontSize: 18, fontWeight: '600' },
  scrollView: { flex: 1 },
  loadingContainer: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  loadingText: { marginTop: 16, color: theme.colors.onSurfaceVariant },
  errorContainer: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: 32 },
  errorButton: { marginTop: 16 },
  headerCard: { margin: 16, elevation: 4 },
  headerActions: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 },
  parseChip: { alignSelf: 'flex-start' },
  divider: { marginVertical: 16 },
  detailsGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 12 },
  detailItem: { width: '47%' },
  detailLabel: { fontSize: 12, color: theme.colors.onSurfaceVariant },
  detailValue: { fontSize: 14, fontWeight: '500', marginTop: 2 },
  card: { marginHorizontal: 16, marginBottom: 16, elevation: 2 },
  centeredBlock: { alignItems: 'center', paddingVertical: 24 },
  noDataText: { color: theme.colors.onSurfaceVariant, marginTop: 8 },
  hint: { fontSize: 12, color: theme.colors.onSurfaceVariant, marginBottom: 8 },
  resultsSection: { paddingHorizontal: 16, paddingBottom: 16 },
  resultsHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  resultCard: { marginBottom: 12, elevation: 2 },
  resultHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8, gap: 8 },
  testName: { flex: 1, fontSize: 16, fontWeight: '600' },
  chipText: { color: '#fff', fontSize: 10 },
  resultValue: { fontSize: 22, fontWeight: '700', color: theme.colors.primary },
  resultUnit: { fontSize: 16, fontWeight: '400', color: theme.colors.onSurfaceVariant },
  refRange: { fontSize: 13, color: theme.colors.onSurfaceVariant, marginTop: 4, marginBottom: 8 },
  input: { marginBottom: 8 },
  actionRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 8 },
});
