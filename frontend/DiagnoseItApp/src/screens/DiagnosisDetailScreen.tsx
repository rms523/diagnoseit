import React, { useEffect, useState } from 'react';
import {
  View,
  StyleSheet,
  ScrollView,
  RefreshControl,
  Alert,
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
} from 'react-native-paper';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { apiService, Diagnosis } from '../services/api';
import { theme } from '../theme/theme';
import { getConfidenceColor } from '../utils/colors';

export default function DiagnosisDetailScreen({ route, navigation }: any) {
  const { diagnosisId } = route.params;
  const [diagnosis, setDiagnosis] = useState<Diagnosis | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    loadDiagnosis();
  }, [diagnosisId]);

  const loadDiagnosis = async () => {
    try {
      setIsLoading(true);
      const data = await apiService.getDiagnosis(diagnosisId);
      setDiagnosis(data);
    } catch (error) {
      console.error('Error loading diagnosis:', error);
      Alert.alert('Error', 'Failed to load diagnosis details');
    } finally {
      setIsLoading(false);
    }
  };

  const onRefresh = async () => {
    setRefreshing(true);
    await loadDiagnosis();
    setRefreshing(false);
  };

  const getConfidenceText = (score: number) => {
    if (score >= 4) return 'High Confidence';
    if (score >= 3) return 'Medium Confidence';
    return 'Low Confidence';
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    });
  };

  if (isLoading) {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color={theme.colors.primary} />
          <Text style={styles.loadingText}>Loading diagnosis...</Text>
        </View>
      </SafeAreaView>
    );
  }

  if (!diagnosis) {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.errorContainer}>
          <Ionicons name="alert-circle" size={64} color={theme.colors.error} />
          <Title>Diagnosis Not Found</Title>
          <Paragraph>The requested diagnosis could not be found.</Paragraph>
          <Button
            mode="contained"
            onPress={() => navigation.goBack()}
            style={styles.errorButton}
          >
            Go Back
          </Button>
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
        {/* Header Card */}
        <Card style={styles.headerCard}>
          <Card.Content>
            <View style={styles.headerContent}>
              <Title style={styles.diagnosisTitle}>{diagnosis.condition_name}</Title>
              <Chip
                style={[
                  styles.confidenceChip,
                  { backgroundColor: getConfidenceColor(diagnosis.confidence_score) }
                ]}
                textStyle={styles.confidenceChipText}
              >
                {getConfidenceText(diagnosis.confidence_score)} ({diagnosis.confidence_score}/5)
              </Chip>
            </View>

            <Divider style={styles.divider} />

            <View style={styles.detailsGrid}>
              <View style={styles.detailItem}>
                <Ionicons name="calendar" size={20} color={theme.colors.onSurfaceVariant} />
                <View style={styles.detailContent}>
                  <Text style={styles.detailLabel}>Generated</Text>
                  <Text style={styles.detailValue}>
                    {formatDate(diagnosis.created_at)}
                  </Text>
                </View>
              </View>

              <View style={styles.detailItem}>
                <Ionicons name="medical" size={20} color={theme.colors.onSurfaceVariant} />
                <View style={styles.detailContent}>
                  <Text style={styles.detailLabel}>Symptoms</Text>
                  <Text style={styles.detailValue}>
                    {diagnosis.symptoms_considered.length} considered
                  </Text>
                </View>
              </View>

              <View style={styles.detailItem}>
                <Ionicons name="document-text" size={20} color={theme.colors.onSurfaceVariant} />
                <View style={styles.detailContent}>
                  <Text style={styles.detailLabel}>Test Results</Text>
                  <Text style={styles.detailValue}>
                    {diagnosis.test_results_considered.length} considered
                  </Text>
                </View>
              </View>

              <View style={styles.detailItem}>
                <Ionicons name="checkmark-circle" size={20} color={theme.colors.onSurfaceVariant} />
                <View style={styles.detailContent}>
                  <Text style={styles.detailLabel}>Follow-up</Text>
                  <Text style={styles.detailValue}>
                    {diagnosis.follow_up_required ? 'Required' : 'Not Required'}
                  </Text>
                </View>
              </View>
            </View>
          </Card.Content>
        </Card>

        {/* Description */}
        <Card style={styles.card}>
          <Card.Content>
            <Title>Condition Description</Title>
            <Paragraph style={styles.descriptionText}>
              {diagnosis.description}
            </Paragraph>
          </Card.Content>
        </Card>

        {/* Recommendations */}
        <Card style={styles.card}>
          <Card.Content>
            <Title>Recommendations</Title>
            <Paragraph style={styles.recommendationsText}>
              {diagnosis.recommendations}
            </Paragraph>
          </Card.Content>
        </Card>

        {/* Follow-up Information */}
        {diagnosis.follow_up_required && (
          <Card style={styles.card}>
            <Card.Content>
              <Title>Follow-up Information</Title>
              <Paragraph style={styles.followUpText}>
                {diagnosis.follow_up_notes}
              </Paragraph>
            </Card.Content>
          </Card>
        )}

        {/* Actions */}
        <Card style={styles.card}>
          <Card.Content>
            <Title>Actions</Title>
            <View style={styles.actionsContainer}>
              <Button
                mode="outlined"
                onPress={() => {
                  // Navigate to symptoms screen
                  navigation.navigate('Symptoms');
                }}
                icon="medical"
                style={styles.actionButton}
              >
                View Symptoms
              </Button>
              <Button
                mode="outlined"
                onPress={() => {
                  // Navigate to reports screen
                  navigation.navigate('Reports');
                }}
                icon="document-text"
                style={styles.actionButton}
              >
                View Reports
              </Button>
            </View>
            <Button
              mode="contained"
              onPress={() => {
                // Generate new diagnosis
                navigation.navigate('Diagnosis');
              }}
              icon="brain"
              style={styles.generateButton}
            >
              Generate New Diagnosis
            </Button>
          </Card.Content>
        </Card>

        {/* Disclaimer */}
        <Card style={styles.disclaimerCard}>
          <Card.Content>
            <View style={styles.disclaimerHeader}>
              <Ionicons name="warning" size={20} color={theme.colors.error} />
              <Title style={styles.disclaimerTitle}>Important Disclaimer</Title>
            </View>
            <Paragraph style={styles.disclaimerText}>
              This AI-generated diagnosis is for informational purposes only and should not replace professional medical advice. 
              Always consult with a qualified healthcare provider for proper diagnosis and treatment.
            </Paragraph>
          </Card.Content>
        </Card>
      </ScrollView>
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
  errorContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 32,
  },
  errorButton: {
    marginTop: 16,
  },
  headerCard: {
    margin: 16,
    elevation: 4,
  },
  headerContent: {
    marginBottom: 16,
  },
  diagnosisTitle: {
    fontSize: 24,
    fontWeight: 'bold',
    marginBottom: 12,
  },
  confidenceChip: {
    alignSelf: 'flex-start',
  },
  confidenceChipText: {
    color: 'white',
    fontSize: 12,
  },
  divider: {
    marginVertical: 16,
  },
  detailsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'space-between',
  },
  detailItem: {
    flexDirection: 'row',
    alignItems: 'center',
    width: '48%',
    marginBottom: 16,
  },
  detailContent: {
    marginLeft: 12,
    flex: 1,
  },
  detailLabel: {
    fontSize: 12,
    color: theme.colors.onSurfaceVariant,
    marginBottom: 2,
  },
  detailValue: {
    fontSize: 14,
    fontWeight: '500',
  },
  card: {
    margin: 16,
    marginTop: 0,
    elevation: 2,
  },
  descriptionText: {
    marginTop: 8,
    lineHeight: 20,
  },
  recommendationsText: {
    marginTop: 8,
    lineHeight: 20,
  },
  followUpText: {
    marginTop: 8,
    lineHeight: 20,
  },
  actionsContainer: {
    flexDirection: 'row',
    justifyContent: 'space-around',
    marginTop: 16,
    marginBottom: 16,
  },
  actionButton: {
    flex: 1,
    marginHorizontal: 8,
  },
  generateButton: {
    marginTop: 8,
    borderRadius: 8,
  },
  disclaimerCard: {
    margin: 16,
    marginTop: 0,
    elevation: 2,
    backgroundColor: theme.colors.errorContainer,
  },
  disclaimerHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 8,
  },
  disclaimerTitle: {
    marginLeft: 8,
    color: theme.colors.error,
    fontSize: 16,
  },
  disclaimerText: {
    color: theme.colors.onErrorContainer,
    fontSize: 12,
    lineHeight: 16,
  },
});