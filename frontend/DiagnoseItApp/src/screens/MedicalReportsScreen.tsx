import React, { useEffect, useState, useCallback } from 'react';
import {
  View,
  StyleSheet,
  FlatList,
  RefreshControl,
  Alert,
} from 'react-native';
import {
  Text,
  Card,
  Title,
  Paragraph,
  Button,
  FAB,
  Chip,
  Searchbar,
  Menu,
  ActivityIndicator,
  IconButton,
} from 'react-native-paper';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { apiService, MedicalReport } from '../services/api';
import { theme } from '../theme/theme';
import {
  isReportParsing,
  reportMatchesFilter,
  statusBadgeClass,
  statusLabel,
  type ReportStatusFilter,
} from '../utils/reportStatus';
import { badgeColor, getReportTypeColor } from '../utils/colors';

const STATUS_FILTERS: { key: ReportStatusFilter; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'parsed', label: 'Parsed' },
  { key: 'processing', label: 'Processing' },
  { key: 'failed', label: 'Failed' },
];

export default function MedicalReportsScreen({ navigation }: any) {
  const [reports, setReports] = useState<MedicalReport[]>([]);
  const [filteredReports, setFilteredReports] = useState<MedicalReport[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [sortMenuVisible, setSortMenuVisible] = useState(false);
  const [uploadMenuVisible, setUploadMenuVisible] = useState(false);
  const [sortBy, setSortBy] = useState('date');
  const [statusFilter, setStatusFilter] = useState<ReportStatusFilter>('all');

  const loadReports = useCallback(async (silent = false) => {
    try {
      if (!silent) setIsLoading(true);
      const data = await apiService.getMedicalReports();
      setReports(data);
    } catch (error) {
      console.error('Error loading reports:', error);
      if (!silent) Alert.alert('Error', 'Failed to load medical reports');
    } finally {
      if (!silent) setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadReports();
  }, [loadReports]);

  useEffect(() => {
    if (!reports.some(r => isReportParsing(r.status))) return;
    const id = setInterval(() => loadReports(true), 5000);
    return () => clearInterval(id);
  }, [reports, loadReports]);

  const onRefresh = async () => {
    setRefreshing(true);
    await loadReports();
    setRefreshing(false);
  };

  const filterAndSortReports = () => {
    let filtered = reports.filter(r => reportMatchesFilter(r, statusFilter));

    // Filter by search query
    if (searchQuery.trim()) {
      filtered = filtered.filter(
        report =>
          report.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
          report.lab_name?.toLowerCase().includes(searchQuery.toLowerCase()) ||
          report.report_type.toLowerCase().includes(searchQuery.toLowerCase())
      );
    }

    // Sort reports
    filtered.sort((a, b) => {
      switch (sortBy) {
        case 'date':
          return new Date(`${b.report_date}T00:00:00`).getTime() - new Date(`${a.report_date}T00:00:00`).getTime();
        case 'title':
          return a.title.localeCompare(b.title);
        case 'type':
          return a.report_type.localeCompare(b.report_type);
        default:
          return 0;
      }
    });

    setFilteredReports(filtered);
  };

  useEffect(() => {
    filterAndSortReports();
  }, [reports, searchQuery, sortBy, statusFilter]);

  const statusCounts = {
    all: reports.length,
    parsed: reports.filter(r => reportMatchesFilter(r, 'parsed')).length,
    processing: reports.filter(r => reportMatchesFilter(r, 'processing')).length,
    failed: reports.filter(r => reportMatchesFilter(r, 'failed')).length,
  };

  const getStatusColor = (report: MedicalReport) =>
    badgeColor(statusBadgeClass(report.status, report.is_parsed));

  const confirmDelete = (id: number, title: string) => {
    Alert.alert('Delete Report', `Delete "${title}"?`, [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Delete',
        style: 'destructive',
        onPress: async () => {
          try {
            await apiService.deleteMedicalReport(id);
            setReports(prev => prev.filter(r => r.id !== id));
          } catch {
            Alert.alert('Error', 'Failed to delete report');
          }
        },
      },
    ]);
  };

  const renderReportItem = ({ item }: { item: MedicalReport }) => (
    <Card style={styles.reportCard} onPress={() => navigation.navigate('ReportDetail', { reportId: item.id })}>
      <Card.Content>
        <View style={styles.reportHeader}>
          <Title style={styles.reportTitle} numberOfLines={2}>
            {item.title}
          </Title>
          <Chip
            style={[styles.typeChip, { backgroundColor: getReportTypeColor(item.report_type) }]}
            textStyle={styles.typeChipText}
          >
            {item.report_type}
          </Chip>
          <IconButton
            icon="delete-outline"
            size={20}
            iconColor={theme.colors.error}
            onPress={() => confirmDelete(item.id, item.title)}
          />
        </View>
        
        <View style={styles.reportDetails}>
          <View style={styles.detailRow}>
            <Ionicons name="business" size={16} color={theme.colors.onSurfaceVariant} />
            <Text style={styles.detailText}>
              {item.lab_name || 'Unknown Lab'}
            </Text>
          </View>
          
          <View style={styles.detailRow}>
            <Ionicons name="calendar" size={16} color={theme.colors.onSurfaceVariant} />
            <Text style={styles.detailText}>
              {new Date(`${item.report_date}T00:00:00`).toLocaleDateString()}
            </Text>
          </View>
          
          <View style={styles.detailRow}>
            <Ionicons name="document-text" size={16} color={theme.colors.onSurfaceVariant} />
            <Text style={styles.detailText}>
              {statusLabel(item.status, item.is_parsed)}
            </Text>
            {isReportParsing(item.status) ? (
              <ActivityIndicator size={12} style={{ marginLeft: 8 }} />
            ) : (
              <View
                style={[
                  styles.statusDot,
                  { backgroundColor: getStatusColor(item) }
                ]}
              />
            )}
          </View>
        </View>

        {item.test_results && item.test_results.length > 0 && (
          <View style={styles.testResults}>
            <Text style={styles.testResultsText}>
              {item.test_results.length} test result{item.test_results.length !== 1 ? 's' : ''}
            </Text>
          </View>
        )}
      </Card.Content>
    </Card>
  );

  const renderEmptyState = () => (
    <View style={styles.emptyState}>
      <Ionicons name="document-text" size={64} color={theme.colors.onSurfaceVariant} />
      <Title style={styles.emptyTitle}>No Medical Reports</Title>
      <Paragraph style={styles.emptyDescription}>
        Upload your first medical report to get started with health tracking.
      </Paragraph>
      <Button
        mode="contained"
        onPress={() => navigation.navigate('UploadReport')}
        style={styles.emptyButton}
        icon="upload"
      >
        Upload Report
      </Button>
    </View>
  );

  if (isLoading) {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color={theme.colors.primary} />
          <Text style={styles.loadingText}>Loading reports...</Text>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <Title style={styles.headerTitle}>Medical Reports</Title>
        <View style={{ flexDirection: 'row', gap: 8 }}>
          <Menu
            visible={uploadMenuVisible}
            onDismiss={() => setUploadMenuVisible(false)}
            anchor={
              <Button mode="contained" onPress={() => setUploadMenuVisible(true)} icon="upload" compact>
                Upload
              </Button>
            }
          >
            <Menu.Item
              onPress={() => { setUploadMenuVisible(false); navigation.navigate('UploadReport', { mode: 'single' }); }}
              title="Single report"
            />
            <Menu.Item
              onPress={() => { setUploadMenuVisible(false); navigation.navigate('UploadReport', { mode: 'bulk' }); }}
              title="Bulk upload"
            />
          </Menu>
          <Menu
            visible={sortMenuVisible}
            onDismiss={() => setSortMenuVisible(false)}
            anchor={
              <Button
                mode="outlined"
                onPress={() => setSortMenuVisible(true)}
                icon="sort"
                compact
              >
                Sort
              </Button>
            }
          >
            <Menu.Item onPress={() => { setSortBy('date'); setSortMenuVisible(false); }} title="Date" />
            <Menu.Item onPress={() => { setSortBy('title'); setSortMenuVisible(false); }} title="Title" />
            <Menu.Item onPress={() => { setSortBy('type'); setSortMenuVisible(false); }} title="Type" />
          </Menu>
        </View>
      </View>

      <Searchbar
        placeholder="Search reports..."
        onChangeText={setSearchQuery}
        value={searchQuery}
        style={styles.searchBar}
      />

      {reports.length > 0 && (
        <View style={styles.filterRow}>
          {STATUS_FILTERS.map(({ key, label }) => (
            <Chip
              key={key}
              selected={statusFilter === key}
              onPress={() => setStatusFilter(key)}
              style={styles.filterChip}
              compact
            >
              {label} ({statusCounts[key]})
            </Chip>
          ))}
        </View>
      )}

      <FlatList
        data={filteredReports}
        renderItem={renderReportItem}
        keyExtractor={(item) => item.id.toString()}
        contentContainerStyle={styles.listContainer}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} />
        }
        ListEmptyComponent={renderEmptyState}
        showsVerticalScrollIndicator={false}
      />

      <FAB
        style={styles.fab}
        icon="plus"
        onPress={() => navigation.navigate('UploadReport')}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: theme.colors.background,
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  loadingText: {
    marginTop: 16,
    color: theme.colors.onSurfaceVariant,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 20,
    paddingBottom: 10,
  },
  headerTitle: {
    fontSize: 24,
    fontWeight: 'bold',
  },
  searchBar: {
    margin: 16,
    marginTop: 0,
  },
  filterRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    paddingHorizontal: 16,
    marginBottom: 8,
  },
  filterChip: {
    marginBottom: 4,
  },
  listContainer: {
    padding: 16,
    paddingTop: 0,
  },
  reportCard: {
    marginBottom: 16,
    elevation: 2,
  },
  reportHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: 12,
  },
  reportTitle: {
    flex: 1,
    marginRight: 8,
  },
  typeChip: {
    marginLeft: 8,
  },
  typeChipText: {
    color: 'white',
    fontSize: 12,
  },
  reportDetails: {
    marginBottom: 8,
  },
  detailRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 4,
  },
  detailText: {
    marginLeft: 8,
    color: theme.colors.onSurfaceVariant,
    fontSize: 14,
  },
  statusDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    marginLeft: 8,
  },
  testResults: {
    marginTop: 8,
    paddingTop: 8,
    borderTopWidth: 1,
    borderTopColor: theme.colors.outline,
  },
  testResultsText: {
    color: theme.colors.primary,
    fontSize: 14,
    fontWeight: '500',
  },
  emptyState: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingVertical: 64,
  },
  emptyTitle: {
    marginTop: 16,
    textAlign: 'center',
  },
  emptyDescription: {
    textAlign: 'center',
    marginTop: 8,
    marginBottom: 24,
    color: theme.colors.onSurfaceVariant,
  },
  emptyButton: {
    borderRadius: 8,
  },
  fab: {
    position: 'absolute',
    margin: 16,
    right: 0,
    bottom: 0,
    backgroundColor: theme.colors.primary,
  },
});
