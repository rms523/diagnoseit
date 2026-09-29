import React, { useEffect, useState } from 'react';
import {
  View,
  StyleSheet,
  ScrollView,
  RefreshControl,
  Dimensions,
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
} from 'react-native-paper';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useAuth } from '../context/AuthContext';
import { apiService, MedicalReport, Symptom, Diagnosis } from '../services/api';
import { theme } from '../theme/theme';
import { tokens } from '../theme/tokens';
import { getSeverityColor, getConfidenceColor } from '../utils/colors';
import AppText from '../components/AppText';
import { cardStyle } from '../components/AppText';

const { width } = Dimensions.get('window');

export default function DashboardScreen({ navigation }: any) {
  const { user } = useAuth();
  const [recentReports, setRecentReports] = useState<MedicalReport[]>([]);
  const [activeSymptoms, setActiveSymptoms] = useState<Symptom[]>([]);
  const [recentDiagnoses, setRecentDiagnoses] = useState<Diagnosis[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    loadDashboardData();
  }, []);

  const loadDashboardData = async () => {
    try {
      setIsLoading(true);
      const [reports, symptoms, diagnoses] = await Promise.all([
        apiService.getMedicalReports(),
        apiService.getActiveSymptoms(),
        apiService.getDiagnoses(),
      ]);
      
      setRecentReports(reports.slice(0, 3));
      setActiveSymptoms(symptoms.slice(0, 3));
      setRecentDiagnoses(diagnoses.slice(0, 3));
    } catch (error) {
      console.error('Error loading dashboard data:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const onRefresh = async () => {
    setRefreshing(true);
    await loadDashboardData();
    setRefreshing(false);
  };

  const getGreeting = () => {
    const hour = new Date().getHours();
    if (hour < 12) return 'Good Morning';
    if (hour < 18) return 'Good Afternoon';
    return 'Good Evening';
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

  if (isLoading) {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color={theme.colors.primary} />
          <Text style={styles.loadingText}>Loading your health data...</Text>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView
        style={styles.scrollView}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} />
        }
      >
        {/* Header */}
        <View style={styles.header}>
          <View>
            <AppText variant="caption">{getGreeting()}</AppText>
            <AppText variant="display" style={styles.userName}>
              {user?.first_name || user?.username}
            </AppText>
          </View>
          <Button
            mode="outlined"
            onPress={() => navigation.navigate('Profile')}
            icon="account"
            compact
            textColor={tokens.teal}
          >
            Profile
          </Button>
        </View>

        {/* Quick Actions */}
        <Card style={[styles.card, cardStyle.surface]}>
          <Card.Content>
            <Title>Quick Actions</Title>
            <View style={styles.quickActions}>
              <Button
                mode="contained"
                onPress={() => navigation.navigate('UploadReport')}
                style={styles.actionButton}
                icon="upload"
              >
                Upload Report
              </Button>
              <Button
                mode="contained"
                onPress={() => navigation.navigate('AddSymptom')}
                style={styles.actionButton}
                icon="plus"
              >
                Add Symptom
              </Button>
            </View>
          </Card.Content>
        </Card>

        {/* Active Symptoms */}
        {activeSymptoms.length > 0 && (
          <Card style={styles.card}>
            <Card.Content>
              <View style={styles.cardHeader}>
                <Title>Active Symptoms</Title>
                <Button
                  mode="text"
                  onPress={() => navigation.navigate('Symptoms')}
                  compact
                >
                  View All
                </Button>
              </View>
              {activeSymptoms.map((symptom) => (
                <View key={symptom.id} style={styles.symptomItem}>
                  <View style={styles.symptomInfo}>
                    <Text style={styles.symptomDescription}>
                      {symptom.description}
                    </Text>
                    <Text style={styles.symptomDuration}>
                      {symptom.duration} • {symptom.body_part || 'General'}
                    </Text>
                  </View>
                  <Chip
                    style={[
                      styles.severityChip,
                      { backgroundColor: getSeverityColor(symptom.severity) },
                    ]}
                    textStyle={styles.severityText}
                  >
                    {getSeverityText(symptom.severity)}
                  </Chip>
                </View>
              ))}
            </Card.Content>
          </Card>
        )}

        {/* Recent Reports */}
        {recentReports.length > 0 && (
          <Card style={styles.card}>
            <Card.Content>
              <View style={styles.cardHeader}>
                <Title>Recent Reports</Title>
                <Button
                  mode="text"
                  onPress={() => navigation.navigate('Reports')}
                  compact
                >
                  View All
                </Button>
              </View>
              {recentReports.map((report) => (
                <View key={report.id} style={styles.reportItem}>
                  <View style={styles.reportInfo}>
                    <Text style={styles.reportTitle}>{report.title}</Text>
                    <Text style={styles.reportDetails}>
                      {report.report_type} • {report.lab_name || 'Unknown Lab'}
                    </Text>
                    <Text style={styles.reportDate}>
                      {new Date(`${report.report_date}T00:00:00`).toLocaleDateString()}
                    </Text>
                  </View>
                  <Button
                    mode="outlined"
                    onPress={() => navigation.navigate('ReportDetail', { reportId: report.id })}
                    compact
                  >
                    View
                  </Button>
                </View>
              ))}
            </Card.Content>
          </Card>
        )}

        {/* Recent Diagnoses */}
        {recentDiagnoses.length > 0 && (
          <Card style={styles.card}>
            <Card.Content>
              <View style={styles.cardHeader}>
                <Title>Recent Diagnoses</Title>
                <Button
                  mode="text"
                  onPress={() => navigation.navigate('Diagnosis')}
                  compact
                >
                  View All
                </Button>
              </View>
              {recentDiagnoses.map((diagnosis) => (
                <View key={diagnosis.id} style={styles.diagnosisItem}>
                  <View style={styles.diagnosisInfo}>
                    <Text style={styles.diagnosisTitle}>
                      {diagnosis.condition_name}
                    </Text>
                    <Text style={styles.diagnosisDescription}>
                      {diagnosis.description}
                    </Text>
                    <Text style={styles.diagnosisDate}>
                      {new Date(diagnosis.created_at).toLocaleDateString()}
                    </Text>
                  </View>
                  <Chip
                    style={[
                      styles.confidenceChip,
                      {
                        backgroundColor: getConfidenceColor(diagnosis.confidence_score),
                      },
                    ]}
                    textStyle={styles.confidenceText}
                  >
                    {diagnosis.confidence_score}/5
                  </Chip>
                </View>
              ))}
            </Card.Content>
          </Card>
        )}

        {/* Empty State */}
        {activeSymptoms.length === 0 && recentReports.length === 0 && recentDiagnoses.length === 0 && (
          <Card style={styles.card}>
            <Card.Content style={styles.emptyState}>
              <Ionicons name="medical" size={64} color={theme.colors.onSurfaceVariant} />
              <Title style={styles.emptyTitle}>Welcome to DiagnoseIt!</Title>
              <Paragraph style={styles.emptyDescription}>
                Start by uploading your medical reports or adding symptoms to get personalized health insights.
              </Paragraph>
              <Button
                mode="contained"
                onPress={() => navigation.navigate('UploadReport')}
                style={styles.emptyButton}
                icon="upload"
              >
                Upload Your First Report
              </Button>
            </Card.Content>
          </Card>
        )}
      </ScrollView>

      <FAB
        style={styles.fab}
        icon="plus"
        onPress={() => {
          // Show action sheet or modal for quick actions
          navigation.navigate('AddSymptom');
        }}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: theme.colors.background,
  },
  scrollView: {
    flex: 1,
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
  greeting: {
    fontSize: 16,
    color: theme.colors.onSurfaceVariant,
  },
  userName: {
    fontSize: 24,
    fontWeight: 'bold',
    color: theme.colors.onBackground,
  },
  card: {
    margin: 16,
    marginTop: 8,
    elevation: 2,
  },
  cardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 16,
  },
  quickActions: {
    flexDirection: 'row',
    justifyContent: 'space-around',
    marginTop: 16,
  },
  actionButton: {
    flex: 1,
    marginHorizontal: 8,
  },
  symptomItem: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.outline,
  },
  symptomInfo: {
    flex: 1,
  },
  symptomDescription: {
    fontSize: 16,
    fontWeight: '500',
  },
  symptomDuration: {
    fontSize: 14,
    color: theme.colors.onSurfaceVariant,
    marginTop: 2,
  },
  severityChip: {
    marginLeft: 8,
  },
  severityText: {
    color: 'white',
    fontSize: 12,
  },
  reportItem: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.outline,
  },
  reportInfo: {
    flex: 1,
  },
  reportTitle: {
    fontSize: 16,
    fontWeight: '500',
  },
  reportDetails: {
    fontSize: 14,
    color: theme.colors.onSurfaceVariant,
    marginTop: 2,
  },
  reportDate: {
    fontSize: 12,
    color: theme.colors.onSurfaceVariant,
    marginTop: 2,
  },
  diagnosisItem: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.outline,
  },
  diagnosisInfo: {
    flex: 1,
  },
  diagnosisTitle: {
    fontSize: 16,
    fontWeight: '500',
  },
  diagnosisDescription: {
    fontSize: 14,
    color: theme.colors.onSurfaceVariant,
    marginTop: 2,
  },
  diagnosisDate: {
    fontSize: 12,
    color: theme.colors.onSurfaceVariant,
    marginTop: 2,
  },
  confidenceChip: {
    marginLeft: 8,
  },
  confidenceText: {
    color: 'white',
    fontSize: 12,
  },
  emptyState: {
    alignItems: 'center',
    paddingVertical: 32,
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
