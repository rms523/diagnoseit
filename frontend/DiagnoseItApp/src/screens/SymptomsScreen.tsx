import React, { useEffect, useState } from 'react';
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
  SegmentedButtons,
  IconButton,
} from 'react-native-paper';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { apiService, Symptom } from '../services/api';
import { theme } from '../theme/theme';
import { getSeverityColor } from '../utils/colors';

export default function SymptomsScreen({ navigation }: any) {
  const [symptoms, setSymptoms] = useState<Symptom[]>([]);
  const [filteredSymptoms, setFilteredSymptoms] = useState<Symptom[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [filterType, setFilterType] = useState('all');
  const [sortMenuVisible, setSortMenuVisible] = useState(false);
  const [sortBy, setSortBy] = useState('date');

  const filterButtons = [
    { value: 'all', label: 'All' },
    { value: 'active', label: 'Active' },
    { value: 'resolved', label: 'Resolved' },
  ];

  useEffect(() => {
    loadSymptoms();
  }, []);

  useEffect(() => {
    filterAndSortSymptoms();
  }, [symptoms, searchQuery, filterType, sortBy]);

  const loadSymptoms = async () => {
    try {
      setIsLoading(true);
      const data = await apiService.getSymptoms();
      setSymptoms(data);
    } catch (error) {
      console.error('Error loading symptoms:', error);
      Alert.alert('Error', 'Failed to load symptoms');
    } finally {
      setIsLoading(false);
    }
  };

  const onRefresh = async () => {
    setRefreshing(true);
    await loadSymptoms();
    setRefreshing(false);
  };

  const filterAndSortSymptoms = () => {
    let filtered = symptoms;

    // Filter by type
    if (filterType === 'active') {
      filtered = filtered.filter(symptom => symptom.is_ongoing);
    } else if (filterType === 'resolved') {
      filtered = filtered.filter(symptom => !symptom.is_ongoing);
    }

    // Filter by search query
    if (searchQuery.trim()) {
      filtered = filtered.filter(
        symptom =>
          symptom.description.toLowerCase().includes(searchQuery.toLowerCase()) ||
          symptom.body_part?.toLowerCase().includes(searchQuery.toLowerCase())
      );
    }

    // Sort symptoms
    filtered.sort((a, b) => {
      switch (sortBy) {
        case 'date':
          return new Date(b.onset_date).getTime() - new Date(a.onset_date).getTime();
        case 'severity':
          return b.severity - a.severity;
        case 'description':
          return a.description.localeCompare(b.description);
        default:
          return 0;
      }
    });

    setFilteredSymptoms(filtered);
  };

  const getSeverityText = (severity: number) => {
    switch (severity) {
      case 1: return 'Mild';
      case 2: return 'Moderate';
      case 3: return 'Severe';
      case 4: return 'Critical';
      default: return 'Unknown';
    }
  };

  const getDurationText = (duration: string) => {
    switch (duration) {
      case 'ACUTE': return 'Acute';
      case 'SUBACUTE': return 'Subacute';
      case 'CHRONIC': return 'Chronic';
      default: return duration;
    }
  };

  const confirmDelete = (id: number) => {
    Alert.alert('Delete Symptom', 'Delete this symptom record?', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Delete',
        style: 'destructive',
        onPress: async () => {
          try {
            await apiService.deleteSymptom(id);
            setSymptoms(prev => prev.filter(s => s.id !== id));
          } catch {
            Alert.alert('Error', 'Failed to delete symptom');
          }
        },
      },
    ]);
  };

  const renderSymptomItem = ({ item }: { item: Symptom }) => (
    <Card 
      style={styles.symptomCard} 
      onPress={() => navigation.navigate('SymptomDetail', { symptomId: item.id })}
    >
      <Card.Content>
        <View style={styles.symptomHeader}>
          <View style={styles.symptomInfo}>
            <Text style={styles.symptomDescription} numberOfLines={2}>
              {item.description}
            </Text>
            <View style={styles.symptomMeta}>
              <Text style={styles.symptomMetaText}>
                {item.body_part || 'General'} • {getDurationText(item.duration)}
              </Text>
              <Text style={styles.symptomDate}>
                {new Date(item.onset_date).toLocaleDateString()}
              </Text>
            </View>
          </View>
          <View style={styles.symptomBadges}>
            <Chip
              style={[
                styles.severityChip,
                { backgroundColor: getSeverityColor(item.severity) }
              ]}
              textStyle={styles.severityChipText}
            >
              {getSeverityText(item.severity)}
            </Chip>
            <Chip
              style={[
                styles.statusChip,
                { 
                  backgroundColor: item.is_ongoing 
                    ? theme.colors.error 
                    : theme.colors.primary 
                }
              ]}
              textStyle={styles.statusChipText}
            >
              {item.is_ongoing ? 'Active' : 'Resolved'}
            </Chip>
            <IconButton
              icon="delete-outline"
              size={20}
              iconColor={theme.colors.error}
              onPress={() => confirmDelete(item.id)}
            />
          </View>
        </View>
        
        {item.notes && (
          <Text style={styles.symptomNotes} numberOfLines={2}>
            {item.notes}
          </Text>
        )}
      </Card.Content>
    </Card>
  );

  const renderEmptyState = () => (
    <View style={styles.emptyState}>
      <Ionicons name="medical" size={64} color={theme.colors.onSurfaceVariant} />
      <Title style={styles.emptyTitle}>No Symptoms Recorded</Title>
      <Paragraph style={styles.emptyDescription}>
        Start tracking your symptoms to get better health insights.
      </Paragraph>
      <Button
        mode="contained"
        onPress={() => navigation.navigate('AddSymptom')}
        style={styles.emptyButton}
        icon="plus"
      >
        Add First Symptom
      </Button>
    </View>
  );

  if (isLoading) {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color={theme.colors.primary} />
          <Text style={styles.loadingText}>Loading symptoms...</Text>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <Title style={styles.headerTitle}>Symptoms</Title>
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
          <Menu.Item onPress={() => { setSortBy('severity'); setSortMenuVisible(false); }} title="Severity" />
          <Menu.Item onPress={() => { setSortBy('description'); setSortMenuVisible(false); }} title="Description" />
        </Menu>
      </View>

      <Searchbar
        placeholder="Search symptoms..."
        onChangeText={setSearchQuery}
        value={searchQuery}
        style={styles.searchBar}
      />

      <SegmentedButtons
        value={filterType}
        onValueChange={setFilterType}
        buttons={filterButtons}
        style={styles.filterButtons}
      />

      <FlatList
        data={filteredSymptoms}
        renderItem={renderSymptomItem}
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
        onPress={() => navigation.navigate('AddSymptom')}
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
  filterButtons: {
    marginHorizontal: 16,
    marginBottom: 16,
  },
  listContainer: {
    padding: 16,
    paddingTop: 0,
  },
  symptomCard: {
    marginBottom: 16,
    elevation: 2,
  },
  symptomHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: 8,
  },
  symptomInfo: {
    flex: 1,
    marginRight: 12,
  },
  symptomDescription: {
    fontSize: 16,
    fontWeight: '500',
    marginBottom: 4,
  },
  symptomMeta: {
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  symptomMetaText: {
    fontSize: 12,
    color: theme.colors.onSurfaceVariant,
  },
  symptomDate: {
    fontSize: 12,
    color: theme.colors.onSurfaceVariant,
  },
  symptomBadges: {
    alignItems: 'flex-end',
  },
  severityChip: {
    marginBottom: 4,
  },
  severityChipText: {
    color: 'white',
    fontSize: 10,
  },
  statusChip: {
    marginLeft: 0,
  },
  statusChipText: {
    color: 'white',
    fontSize: 10,
  },
  symptomNotes: {
    fontSize: 14,
    color: theme.colors.onSurfaceVariant,
    fontStyle: 'italic',
    marginTop: 8,
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
