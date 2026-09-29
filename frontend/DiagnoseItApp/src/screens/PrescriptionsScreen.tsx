import React, { useCallback, useEffect, useState } from 'react';
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
import { useFocusEffect } from '@react-navigation/native';
import { apiService, Prescription } from '../services/api';
import { theme } from '../theme/theme';
import { isReportParsing, statusBadgeClass, statusLabel } from '../utils/reportStatus';
import { badgeColor } from '../utils/colors';

export default function PrescriptionsScreen({ navigation }: any) {
  const [prescriptions, setPrescriptions] = useState<Prescription[]>([]);
  const [filteredPrescriptions, setFilteredPrescriptions] = useState<Prescription[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [sortMenuVisible, setSortMenuVisible] = useState(false);
  const [sortBy, setSortBy] = useState('date');

  useEffect(() => {
    filterAndSortPrescriptions();
  }, [prescriptions, searchQuery, sortBy]);

  const loadPrescriptions = useCallback(async (silent = false) => {
    try {
      if (!silent) setIsLoading(true);
      const data = await apiService.getPrescriptions();
      setPrescriptions(data);
    } catch (error) {
      console.error('Error loading prescriptions:', error);
      if (!silent) Alert.alert('Error', 'Failed to load prescriptions');
    } finally {
      if (!silent) setIsLoading(false);
    }
  }, []);

  useFocusEffect(useCallback(() => {
    loadPrescriptions();
  }, [loadPrescriptions]));

  useEffect(() => {
    if (!prescriptions.some(item => isReportParsing(item.status))) return;
    const id = setInterval(() => loadPrescriptions(true), 5000);
    return () => clearInterval(id);
  }, [prescriptions, loadPrescriptions]);

  const onRefresh = async () => {
    setRefreshing(true);
    await loadPrescriptions();
    setRefreshing(false);
  };

  const filterAndSortPrescriptions = () => {
    let filtered = [...prescriptions];

    // Filter by search query
    if (searchQuery.trim()) {
      filtered = filtered.filter(
        prescription =>
          prescription.doctor_name?.toLowerCase().includes(searchQuery.toLowerCase()) ||
          prescription.hospital_clinic?.toLowerCase().includes(searchQuery.toLowerCase()) ||
          prescription.notes?.toLowerCase().includes(searchQuery.toLowerCase())
      );
    }

    // Sort prescriptions
    filtered.sort((a, b) => {
      switch (sortBy) {
        case 'date':
          return new Date(`${b.prescription_date}T00:00:00`).getTime() - new Date(`${a.prescription_date}T00:00:00`).getTime();
        case 'doctor':
          return (a.doctor_name || '').localeCompare(b.doctor_name || '');
        case 'hospital':
          return (a.hospital_clinic || '').localeCompare(b.hospital_clinic || '');
        default:
          return 0;
      }
    });

    setFilteredPrescriptions(filtered);
  };

  const getStatusColor = (item: Prescription) =>
    badgeColor(statusBadgeClass(item.status, item.is_parsed));

  const confirmDelete = (id: number, label: string) => {
    Alert.alert('Delete Prescription', `Delete prescription from ${label}?`, [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Delete',
        style: 'destructive',
        onPress: async () => {
          try {
            await apiService.deletePrescription(id);
            setPrescriptions(prev => prev.filter(p => p.id !== id));
          } catch {
            Alert.alert('Error', 'Failed to delete prescription');
          }
        },
      },
    ]);
  };

  const renderPrescriptionItem = ({ item }: { item: Prescription }) => (
    <Card 
      style={styles.prescriptionCard} 
      onPress={() => navigation.navigate('PrescriptionDetail', { prescriptionId: item.id })}
    >
      <Card.Content>
        <View style={styles.prescriptionHeader}>
          <View style={styles.prescriptionInfo}>
            <Title style={styles.doctorName} numberOfLines={1}>
              {item.doctor_name || 'Unknown Doctor'}
            </Title>
            <Text style={styles.hospitalName} numberOfLines={1}>
              {item.hospital_clinic || 'Unknown Clinic'}
            </Text>
          </View>
          <View style={styles.prescriptionBadges}>
            <Chip
              style={[
                styles.statusChip,
                { backgroundColor: getStatusColor(item) }
              ]}
              textStyle={styles.statusChipText}
            >
              {statusLabel(item.status, item.is_parsed)}
            </Chip>
            {isReportParsing(item.status) && <ActivityIndicator size={14} style={{ marginTop: 6 }} />}
            <IconButton
              icon="delete-outline"
              size={20}
              iconColor={theme.colors.error}
              onPress={() => confirmDelete(item.id, item.doctor_name || 'Unknown Doctor')}
            />
          </View>
        </View>
        
        <View style={styles.prescriptionDetails}>
          <View style={styles.detailRow}>
            <Ionicons name="calendar" size={16} color={theme.colors.onSurfaceVariant} />
            <Text style={styles.detailText}>
              {new Date(`${item.prescription_date}T00:00:00`).toLocaleDateString()}
            </Text>
          </View>
          
          <View style={styles.detailRow}>
            <Ionicons name="document-text" size={16} color={theme.colors.onSurfaceVariant} />
            <Text style={styles.detailText}>
              {item.medications?.length || 0} medication{(item.medications?.length || 0) !== 1 ? 's' : ''}
            </Text>
          </View>
          
          <View style={styles.detailRow}>
            <Ionicons name="time" size={16} color={theme.colors.onSurfaceVariant} />
            <Text style={styles.detailText}>
              {new Date(item.created_at).toLocaleDateString()}
            </Text>
          </View>
        </View>

        {item.notes && (
          <Text style={styles.notesText} numberOfLines={2}>
            {item.notes}
          </Text>
        )}

        {item.status === 'FAILED' && item.parse_error ? (
          <Text style={{ color: theme.colors.error, marginTop: 8 }} numberOfLines={2}>
            {item.parse_error}
          </Text>
        ) : null}

        {item.medications && item.medications.length > 0 && (
          <View style={styles.medicationsPreview}>
            <Text style={styles.medicationsTitle}>Medications:</Text>
            <Text style={styles.medicationsText} numberOfLines={2}>
              {item.medications.map(med => med.medication_name).join(', ')}
            </Text>
          </View>
        )}
      </Card.Content>
    </Card>
  );

  const renderEmptyState = () => (
    <View style={styles.emptyState}>
      <Ionicons name="receipt" size={64} color={theme.colors.onSurfaceVariant} />
      <Title style={styles.emptyTitle}>No Prescriptions</Title>
      <Paragraph style={styles.emptyDescription}>
        Upload your first prescription to start tracking your medications.
      </Paragraph>
      <Button
        mode="contained"
        onPress={() => navigation.navigate('UploadPrescription')}
        style={styles.emptyButton}
        icon="upload"
      >
        Upload Prescription
      </Button>
    </View>
  );

  if (isLoading) {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color={theme.colors.primary} />
          <Text style={styles.loadingText}>Loading prescriptions...</Text>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <Title style={styles.headerTitle}>Prescriptions</Title>
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
          <Menu.Item onPress={() => { setSortBy('doctor'); setSortMenuVisible(false); }} title="Doctor" />
          <Menu.Item onPress={() => { setSortBy('hospital'); setSortMenuVisible(false); }} title="Hospital" />
        </Menu>
      </View>

      <Searchbar
        placeholder="Search prescriptions..."
        onChangeText={setSearchQuery}
        value={searchQuery}
        style={styles.searchBar}
      />

      <FlatList
        data={filteredPrescriptions}
        renderItem={renderPrescriptionItem}
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
        onPress={() => navigation.navigate('UploadPrescription')}
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
  listContainer: {
    padding: 16,
    paddingTop: 0,
  },
  prescriptionCard: {
    marginBottom: 16,
    elevation: 2,
  },
  prescriptionHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: 12,
  },
  prescriptionInfo: {
    flex: 1,
    marginRight: 12,
  },
  doctorName: {
    fontSize: 18,
    fontWeight: 'bold',
    marginBottom: 4,
  },
  hospitalName: {
    fontSize: 14,
    color: theme.colors.onSurfaceVariant,
  },
  prescriptionBadges: {
    alignItems: 'flex-end',
  },
  statusChip: {
    marginLeft: 8,
  },
  statusChipText: {
    color: 'white',
    fontSize: 10,
  },
  prescriptionDetails: {
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
  notesText: {
    fontSize: 14,
    color: theme.colors.onSurfaceVariant,
    fontStyle: 'italic',
    marginTop: 8,
    marginBottom: 8,
  },
  medicationsPreview: {
    marginTop: 8,
    paddingTop: 8,
    borderTopWidth: 1,
    borderTopColor: theme.colors.outline,
  },
  medicationsTitle: {
    fontSize: 12,
    fontWeight: '600',
    color: theme.colors.primary,
    marginBottom: 4,
  },
  medicationsText: {
    fontSize: 14,
    color: theme.colors.onSurfaceVariant,
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
