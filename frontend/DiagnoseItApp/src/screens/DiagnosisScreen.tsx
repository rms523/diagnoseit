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
  ActivityIndicator,
  Checkbox,
  IconButton,
} from 'react-native-paper';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { apiService, Diagnosis, Symptom, MedicalReport } from '../services/api';
import { theme } from '../theme/theme';
import { getConfidenceColor } from '../utils/colors';

export default function DiagnosisScreen({ navigation }: any) {
  const [diagnoses, setDiagnoses] = useState<Diagnosis[]>([]);
  const [symptoms, setSymptoms] = useState<Symptom[]>([]);
  const [reports, setReports] = useState<MedicalReport[]>([]);
  const [selectedSymptoms, setSelectedSymptoms] = useState<number[]>([]);
  const [selectedReports, setSelectedReports] = useState<number[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [showSelection, setShowSelection] = useState(false);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      setIsLoading(true);
      const [diagnosesData, symptomsData, reportsData] = await Promise.all([
        apiService.getDiagnoses(),
        apiService.getSymptoms(),
        apiService.getMedicalReports(),
      ]);
      
      setDiagnoses(diagnosesData);
      setSymptoms(symptomsData);
      setReports(reportsData);
    } catch (error) {
      console.error('Error loading data:', error);
      Alert.alert('Error', 'Failed to load data');
    } finally {
      setIsLoading(false);
    }
  };

  const onRefresh = async () => {
    setRefreshing(true);
    await loadData();
    setRefreshing(false);
  };

  const generateDiagnosis = async () => {
    if (selectedSymptoms.length === 0) {
      Alert.alert('Error', 'Please select at least one symptom');
      return;
    }

    setIsGenerating(true);
    try {
      const symptomDescriptions = symptoms
        .filter(s => selectedSymptoms.includes(s.id))
        .map(s => s.description);

      const diagnosis = await apiService.generateDiagnosis({
        symptoms: symptomDescriptions,
        include_test_results: selectedReports.length > 0,
        include_medical_history: true,
      });
      
      // Refresh the diagnoses list
      await loadData();
      
      Alert.alert(
        'Diagnosis Generated',
        'New diagnosis has been generated successfully!',
        [
          {
            text: 'View',
            onPress: () => navigation.navigate('DiagnosisDetail', { diagnosisId: diagnosis.id }),
          },
          { text: 'OK' },
        ]
      );
      
      setShowSelection(false);
      setSelectedSymptoms([]);
      setSelectedReports([]);
    } catch (error: any) {
      console.error('Error generating diagnosis:', error);
      Alert.alert('Error', error.message || 'Failed to generate diagnosis');
    } finally {
      setIsGenerating(false);
    }
  };

  const toggleSymptom = (symptomId: number) => {
    setSelectedSymptoms(prev =>
      prev.includes(symptomId)
        ? prev.filter(id => id !== symptomId)
        : [...prev, symptomId]
    );
  };

  const toggleReport = (reportId: number) => {
    setSelectedReports(prev =>
      prev.includes(reportId)
        ? prev.filter(id => id !== reportId)
        : [...prev, reportId]
    );
  };

  const getConfidenceText = (score: number) => {
    if (score >= 4) return 'High';
    if (score >= 3) return 'Medium';
    return 'Low';
  };

  const confirmDelete = (id: number, name: string) => {
    Alert.alert('Delete Diagnosis', `Delete "${name}"?`, [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Delete',
        style: 'destructive',
        onPress: async () => {
          try {
            await apiService.deleteDiagnosis(id);
            setDiagnoses(prev => prev.filter(d => d.id !== id));
          } catch {
            Alert.alert('Error', 'Failed to delete diagnosis');
          }
        },
      },
    ]);
  };

  const renderDiagnosisItem = ({ item }: { item: Diagnosis }) => (
    <Card 
      style={styles.diagnosisCard} 
      onPress={() => navigation.navigate('DiagnosisDetail', { diagnosisId: item.id })}
    >
      <Card.Content>
        <View style={styles.diagnosisHeader}>
          <View style={styles.diagnosisInfo}>
            <Title style={styles.diagnosisTitle}>{item.condition_name}</Title>
            <Paragraph style={styles.diagnosisDescription} numberOfLines={2}>
              {item.description}
            </Paragraph>
          </View>
          <View style={styles.diagnosisBadges}>
            <Chip
              style={[
                styles.confidenceChip,
                { backgroundColor: getConfidenceColor(item.confidence_score) }
              ]}
              textStyle={styles.confidenceChipText}
            >
              {getConfidenceText(item.confidence_score)} ({item.confidence_score}/5)
            </Chip>
            {item.follow_up_required && (
              <Chip
                style={[styles.followUpChip, { backgroundColor: theme.colors.error }]}
                textStyle={styles.followUpChipText}
              >
                Follow-up Required
              </Chip>
            )}
            <IconButton
              icon="delete-outline"
              size={20}
              iconColor={theme.colors.error}
              onPress={() => confirmDelete(item.id, item.condition_name)}
            />
          </View>
        </View>
        
        <View style={styles.diagnosisMeta}>
          <Text style={styles.diagnosisDate}>
            {new Date(item.created_at).toLocaleDateString()}
          </Text>
          <Text style={styles.diagnosisStats}>
            {item.symptoms_considered.length} symptoms, {item.test_results_considered.length} tests
          </Text>
        </View>
      </Card.Content>
    </Card>
  );

  const renderSelectionModal = () => (
    <View style={styles.selectionModal}>
      <Card style={styles.selectionCard}>
        <Card.Content>
          <Title>Select Data for Diagnosis</Title>
          
          <View style={styles.selectionSection}>
            <Text style={styles.sectionTitle}>Active Symptoms</Text>
            {symptoms.filter(s => s.is_ongoing).map((symptom) => (
              <View key={symptom.id} style={styles.selectionItem}>
                <Checkbox
                  status={selectedSymptoms.includes(symptom.id) ? 'checked' : 'unchecked'}
                  onPress={() => toggleSymptom(symptom.id)}
                />
                <Text style={styles.selectionText}>{symptom.description}</Text>
              </View>
            ))}
          </View>

          <View style={styles.selectionSection}>
            <Text style={styles.sectionTitle}>Recent Reports</Text>
            {reports.slice(0, 5).map((report) => (
              <View key={report.id} style={styles.selectionItem}>
                <Checkbox
                  status={selectedReports.includes(report.id) ? 'checked' : 'unchecked'}
                  onPress={() => toggleReport(report.id)}
                />
                <Text style={styles.selectionText}>{report.title}</Text>
              </View>
            ))}
          </View>

          <View style={styles.selectionActions}>
            <Button
              mode="outlined"
              onPress={() => setShowSelection(false)}
              style={styles.selectionButton}
            >
              Cancel
            </Button>
            <Button
              mode="contained"
              onPress={generateDiagnosis}
              style={styles.selectionButton}
              disabled={isGenerating}
            >
              {isGenerating ? (
                <ActivityIndicator color="white" />
              ) : (
                'Generate Diagnosis'
              )}
            </Button>
          </View>
        </Card.Content>
      </Card>
    </View>
  );

  const renderEmptyState = () => (
    <View style={styles.emptyState}>
      <Ionicons name="analytics-outline" size={64} color={theme.colors.onSurfaceVariant} />
      <Title style={styles.emptyTitle}>No Diagnoses Yet</Title>
      <Paragraph style={styles.emptyDescription}>
        Generate AI-powered diagnoses based on your symptoms and medical reports.
      </Paragraph>
      <Button
        mode="contained"
        onPress={() => setShowSelection(true)}
        style={styles.emptyButton}
        icon="brain"
      >
        Generate First Diagnosis
      </Button>
    </View>
  );

  if (isLoading) {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color={theme.colors.primary} />
          <Text style={styles.loadingText}>Loading diagnoses...</Text>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <Title style={styles.headerTitle}>AI Diagnosis</Title>
        <Button
          mode="contained"
          onPress={() => setShowSelection(true)}
          icon="brain"
          compact
        >
          Generate
        </Button>
      </View>

      <FlatList
        data={diagnoses}
        renderItem={renderDiagnosisItem}
        keyExtractor={(item) => item.id.toString()}
        contentContainerStyle={styles.listContainer}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} />
        }
        ListEmptyComponent={renderEmptyState}
        showsVerticalScrollIndicator={false}
      />

      {showSelection && renderSelectionModal()}
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
  listContainer: {
    padding: 16,
    paddingTop: 0,
  },
  diagnosisCard: {
    marginBottom: 16,
    elevation: 2,
  },
  diagnosisHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: 12,
  },
  diagnosisInfo: {
    flex: 1,
    marginRight: 12,
  },
  diagnosisTitle: {
    fontSize: 18,
    fontWeight: 'bold',
    marginBottom: 4,
  },
  diagnosisDescription: {
    fontSize: 14,
    color: theme.colors.onSurfaceVariant,
  },
  diagnosisBadges: {
    alignItems: 'flex-end',
  },
  confidenceChip: {
    marginBottom: 4,
  },
  confidenceChipText: {
    color: 'white',
    fontSize: 10,
  },
  followUpChip: {
    marginLeft: 0,
  },
  followUpChipText: {
    color: 'white',
    fontSize: 10,
  },
  diagnosisMeta: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  diagnosisDate: {
    fontSize: 12,
    color: theme.colors.onSurfaceVariant,
  },
  diagnosisStats: {
    fontSize: 12,
    color: theme.colors.onSurfaceVariant,
  },
  selectionModal: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: 'rgba(0, 0, 0, 0.5)',
    justifyContent: 'center',
    alignItems: 'center',
    zIndex: 1000,
  },
  selectionCard: {
    margin: 20,
    maxHeight: '80%',
    width: '90%',
    elevation: 8,
  },
  selectionSection: {
    marginBottom: 20,
  },
  sectionTitle: {
    fontSize: 16,
    fontWeight: '600',
    marginBottom: 12,
    color: theme.colors.onBackground,
  },
  selectionItem: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 8,
  },
  selectionText: {
    marginLeft: 8,
    flex: 1,
  },
  selectionActions: {
    flexDirection: 'row',
    justifyContent: 'space-around',
    marginTop: 20,
  },
  selectionButton: {
    flex: 1,
    marginHorizontal: 8,
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
});