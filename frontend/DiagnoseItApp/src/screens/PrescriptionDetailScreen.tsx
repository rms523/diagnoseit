import React, { useCallback, useEffect, useState } from 'react';
import {
  View,
  StyleSheet,
  ScrollView,
  RefreshControl,
  Alert,
  Linking,
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
  DataTable,
} from 'react-native-paper';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { apiService, Prescription, Medication, mediaUrl } from '../services/api';
import { theme } from '../theme/theme';
import { isReportParsing, statusLabel } from '../utils/reportStatus';

export default function PrescriptionDetailScreen({ route, navigation }: any) {
  const { prescriptionId } = route.params;
  const [prescription, setPrescription] = useState<Prescription | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const loadPrescription = useCallback(async (silent = false) => {
    try {
      if (!silent) setIsLoading(true);
      const data = await apiService.getPrescription(prescriptionId);
      setPrescription(data);
    } catch (error) {
      console.error('Error loading prescription:', error);
      if (!silent) Alert.alert('Error', 'Failed to load prescription details');
    } finally {
      if (!silent) setIsLoading(false);
    }
  }, [prescriptionId]);

  useEffect(() => {
    loadPrescription();
  }, [loadPrescription]);

  useEffect(() => {
    if (!isReportParsing(prescription?.status)) return;
    const id = setInterval(() => loadPrescription(true), 5000);
    return () => clearInterval(id);
  }, [prescription?.status, loadPrescription]);

  const onRefresh = async () => {
    setRefreshing(true);
    await loadPrescription();
    setRefreshing(false);
  };

  const openFile = async () => {
    if (prescription?.file) {
      try {
        await Linking.openURL(mediaUrl(prescription.file));
      } catch (error) {
        Alert.alert('Error', 'Could not open file');
      }
    }
  };

  const renderMedications = () => {
    if (!prescription?.medications || prescription.medications.length === 0) {
      return (
        <Card style={styles.card}>
          <Card.Content>
            <Title>Medications</Title>
            <Paragraph style={styles.noDataText}>
              No medications found in this prescription.
            </Paragraph>
          </Card.Content>
        </Card>
      );
    }

    return (
      <Card style={styles.card}>
        <Card.Content>
          <Title>Medications ({prescription.medications.length})</Title>
          <DataTable>
            <DataTable.Header>
              <DataTable.Title>Medication</DataTable.Title>
              <DataTable.Title>Dosage</DataTable.Title>
              <DataTable.Title>Frequency</DataTable.Title>
            </DataTable.Header>
            {prescription.medications.map((medication: Medication) => (
              <DataTable.Row key={medication.id}>
                <DataTable.Cell>{medication.medication_name}</DataTable.Cell>
                <DataTable.Cell>{medication.dosage}</DataTable.Cell>
                <DataTable.Cell>{medication.frequency}</DataTable.Cell>
              </DataTable.Row>
            ))}
          </DataTable>
        </Card.Content>
      </Card>
    );
  };

  const renderDetailedMedications = () => {
    if (!prescription?.medications || prescription.medications.length === 0) {
      return null;
    }

    return (
      <Card style={styles.card}>
        <Card.Content>
          <Title>Detailed Medication Information</Title>
          {prescription.medications.map((medication: Medication, index: number) => (
            <View key={medication.id} style={styles.medicationDetail}>
              <Text style={styles.medicationName}>{medication.medication_name}</Text>
              <View style={styles.medicationInfo}>
                <View style={styles.medicationRow}>
                  <Text style={styles.medicationLabel}>Dosage:</Text>
                  <Text style={styles.medicationValue}>{medication.dosage}</Text>
                </View>
                <View style={styles.medicationRow}>
                  <Text style={styles.medicationLabel}>Frequency:</Text>
                  <Text style={styles.medicationValue}>{medication.frequency}</Text>
                </View>
                <View style={styles.medicationRow}>
                  <Text style={styles.medicationLabel}>Duration:</Text>
                  <Text style={styles.medicationValue}>{medication.duration}</Text>
                </View>
                {medication.instructions && (
                  <View style={styles.medicationRow}>
                    <Text style={styles.medicationLabel}>Instructions:</Text>
                    <Text style={styles.medicationValue}>{medication.instructions}</Text>
                  </View>
                )}
              </View>
              {index < prescription.medications.length - 1 && (
                <Divider style={styles.medicationDivider} />
              )}
            </View>
          ))}
        </Card.Content>
      </Card>
    );
  };

  if (isLoading) {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color={theme.colors.primary} />
          <Text style={styles.loadingText}>Loading prescription...</Text>
        </View>
      </SafeAreaView>
    );
  }

  if (!prescription) {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.errorContainer}>
          <Ionicons name="alert-circle" size={64} color={theme.colors.error} />
          <Title>Prescription Not Found</Title>
          <Paragraph>The requested prescription could not be found.</Paragraph>
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
              <View style={styles.titleContainer}>
                <Title style={styles.doctorName}>{prescription.doctor_name || 'Unknown Doctor'}</Title>
                <Text style={styles.hospitalName}>{prescription.hospital_clinic || 'Unknown Clinic'}</Text>
              </View>
              
              <Button
                mode="outlined"
                onPress={openFile}
                icon="download"
                compact
              >
                View File
              </Button>
            </View>

            <Divider style={styles.divider} />

            <View style={styles.detailsGrid}>
              <View style={styles.detailItem}>
                <Ionicons name="calendar" size={20} color={theme.colors.onSurfaceVariant} />
                <View style={styles.detailContent}>
                  <Text style={styles.detailLabel}>Prescription Date</Text>
                  <Text style={styles.detailValue}>
                    {new Date(`${prescription.prescription_date}T00:00:00`).toLocaleDateString()}
                  </Text>
                </View>
              </View>

              <View style={styles.detailItem}>
                <Ionicons name="document-text" size={20} color={theme.colors.onSurfaceVariant} />
                <View style={styles.detailContent}>
                  <Text style={styles.detailLabel}>Status</Text>
                  <Text style={styles.detailValue}>
                    {statusLabel(prescription.status, prescription.is_parsed)}
                  </Text>
                  {isReportParsing(prescription.status) && <ActivityIndicator size={14} />}
                </View>
              </View>

              <View style={styles.detailItem}>
                <Ionicons name="medical" size={20} color={theme.colors.onSurfaceVariant} />
                <View style={styles.detailContent}>
                  <Text style={styles.detailLabel}>Medications</Text>
                  <Text style={styles.detailValue}>
                    {prescription.medications?.length || 0}
                  </Text>
                </View>
              </View>

              <View style={styles.detailItem}>
                <Ionicons name="time" size={20} color={theme.colors.onSurfaceVariant} />
                <View style={styles.detailContent}>
                  <Text style={styles.detailLabel}>Uploaded</Text>
                  <Text style={styles.detailValue}>
                    {new Date(prescription.created_at).toLocaleDateString()}
                  </Text>
                </View>
              </View>
            </View>
          </Card.Content>
        </Card>

        {prescription.status === 'FAILED' && prescription.parse_error ? (
          <Card style={styles.card}>
            <Card.Content>
              <Title>Could not read prescription</Title>
              <Paragraph style={{ color: theme.colors.error }}>{prescription.parse_error}</Paragraph>
            </Card.Content>
          </Card>
        ) : null}

        {/* Medications Table */}
        {renderMedications()}

        {/* Detailed Medications */}
        {renderDetailedMedications()}

        {/* Notes */}
        {prescription.notes && (
          <Card style={styles.card}>
            <Card.Content>
              <Title>Notes</Title>
              <Paragraph style={styles.notesText}>{prescription.notes}</Paragraph>
            </Card.Content>
          </Card>
        )}

        {/* Parsed Data */}
        {prescription.parsed_data && (
          <Card style={styles.card}>
            <Card.Content>
              <Title>Parsed Data</Title>
              <Paragraph style={styles.parsedData}>
                {JSON.stringify(prescription.parsed_data, null, 2)}
              </Paragraph>
            </Card.Content>
          </Card>
        )}
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
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: 16,
  },
  titleContainer: {
    flex: 1,
    marginRight: 16,
  },
  doctorName: {
    fontSize: 20,
    fontWeight: 'bold',
    marginBottom: 4,
  },
  hospitalName: {
    fontSize: 14,
    color: theme.colors.onSurfaceVariant,
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
  noDataText: {
    color: theme.colors.onSurfaceVariant,
    fontStyle: 'italic',
  },
  medicationDetail: {
    marginBottom: 16,
  },
  medicationName: {
    fontSize: 16,
    fontWeight: 'bold',
    marginBottom: 8,
    color: theme.colors.primary,
  },
  medicationInfo: {
    marginLeft: 8,
  },
  medicationRow: {
    flexDirection: 'row',
    marginBottom: 4,
  },
  medicationLabel: {
    fontSize: 14,
    fontWeight: '500',
    width: 100,
    color: theme.colors.onSurfaceVariant,
  },
  medicationValue: {
    fontSize: 14,
    flex: 1,
  },
  medicationDivider: {
    marginTop: 16,
  },
  notesText: {
    marginTop: 8,
    lineHeight: 20,
  },
  parsedData: {
    fontFamily: 'monospace',
    fontSize: 12,
    backgroundColor: theme.colors.surfaceVariant,
    padding: 12,
    borderRadius: 8,
    marginTop: 8,
  },
});
