import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { View, StyleSheet, ScrollView } from 'react-native';
import {
  Text,
  Card,
  Title,
  Paragraph,
  Searchbar,
  Chip,
  ActivityIndicator,
  DataTable,
} from 'react-native-paper';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { apiService, HealthTrendData } from '../services/api';
import { theme } from '../theme/theme';
import { getLabStatusColor } from '../utils/colors';
import TrendChart from '../components/TrendChart';
import { buildPlottablePoints } from '../utils/labNumeric';

export default function HealthTrendsScreen() {
  const [searchTerm, setSearchTerm] = useState('');
  const [availableTests, setAvailableTests] = useState<string[]>([]);
  const [trendData, setTrendData] = useState<HealthTrendData | null>(null);
  const [loading, setLoading] = useState(true);
  const [searchLoading, setSearchLoading] = useState(false);

  useEffect(() => {
    const loadTests = async () => {
      try {
        const reports = await apiService.getMedicalReports();
        const names = new Set<string>();
        reports.forEach(r => {
          r.test_results?.forEach(tr => {
            if (tr.test_name) names.add(tr.test_name);
          });
        });
        setAvailableTests(Array.from(names).sort());
      } catch {
        /* ignore */
      } finally {
        setLoading(false);
      }
    };
    loadTests();
  }, []);

  const searchParameter = useCallback(async (param: string) => {
    if (!param.trim()) return;
    setSearchLoading(true);
    try {
      const data = await apiService.getHealthTrends(param.trim());
      setTrendData(data);
    } catch {
      setTrendData({ parameter: param, trends: [] });
    } finally {
      setSearchLoading(false);
    }
  }, []);

  const filteredSuggestions = useMemo(() => {
    if (!searchTerm.trim()) return availableTests.slice(0, 12);
    const q = searchTerm.toLowerCase();
    return availableTests.filter(t => t.toLowerCase().includes(q)).slice(0, 12);
  }, [availableTests, searchTerm]);

  if (loading) {
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
        <Title style={styles.title}>Health Trends</Title>
        <Paragraph style={styles.subtitle}>Track lab values over time</Paragraph>

        <Searchbar
          placeholder="Search test name…"
          value={searchTerm}
          onChangeText={setSearchTerm}
          onSubmitEditing={() => searchParameter(searchTerm)}
          style={styles.searchBar}
        />

        {filteredSuggestions.length > 0 && (
          <View style={styles.chipRow}>
            {filteredSuggestions.map(name => (
              <Chip
                key={name}
                compact
                style={styles.chip}
                onPress={() => {
                  setSearchTerm(name);
                  searchParameter(name);
                }}
              >
                {name.length > 24 ? `${name.slice(0, 22)}…` : name}
              </Chip>
            ))}
          </View>
        )}

        {searchLoading && (
          <ActivityIndicator style={{ marginVertical: 16 }} color={theme.colors.primary} />
        )}

        {!searchLoading && trendData && (
          <Card style={styles.card}>
            <Card.Content>
              <Title style={styles.cardTitle}>{trendData.parameter}</Title>
              {trendData.trends.length === 0 ? (
                <View style={styles.empty}>
                  <Ionicons name="analytics-outline" size={48} color={theme.colors.onSurfaceVariant} />
                  <Paragraph style={styles.emptyText}>No trend data for this parameter yet.</Paragraph>
                </View>
              ) : (
                <>
                  {buildPlottablePoints(trendData.trends).length > 0 && (
                    <TrendChart trends={trendData.trends} />
                  )}
                  <DataTable>
                  <DataTable.Header>
                    <DataTable.Title>Date</DataTable.Title>
                    <DataTable.Title numeric>Value</DataTable.Title>
                    <DataTable.Title>Unit</DataTable.Title>
                    <DataTable.Title>Status</DataTable.Title>
                  </DataTable.Header>
                  {trendData.trends.map((item, i) => (
                    <DataTable.Row key={`${item.date}-${i}`}>
                      <DataTable.Cell>{new Date(`${item.date}T00:00:00`).toLocaleDateString()}</DataTable.Cell>
                      <DataTable.Cell numeric>{item.value}</DataTable.Cell>
                      <DataTable.Cell>{item.unit}</DataTable.Cell>
                      <DataTable.Cell>
                        <Chip
                          compact
                          style={{ backgroundColor: getLabStatusColor(item.status) }}
                          textStyle={{ color: '#fff', fontSize: 11 }}
                        >
                          {item.status}
                        </Chip>
                      </DataTable.Cell>
                    </DataTable.Row>
                  ))}
                  </DataTable>
                </>
              )}
            </Card.Content>
          </Card>
        )}

        {availableTests.length === 0 && (
          <Card style={styles.card}>
            <Card.Content style={styles.empty}>
              <Paragraph>Upload and parse reports to see available parameters.</Paragraph>
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
  searchBar: { marginBottom: 12 },
  chipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 16 },
  chip: { marginBottom: 4 },
  card: { elevation: 2 },
  cardTitle: { marginBottom: 12 },
  empty: { alignItems: 'center', paddingVertical: 24 },
  emptyText: { marginTop: 8, textAlign: 'center', color: theme.colors.onSurfaceVariant },
});
