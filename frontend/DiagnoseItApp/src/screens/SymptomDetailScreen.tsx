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
  TextInput,
  IconButton,
} from 'react-native-paper';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { apiService, Symptom, SymptomLog } from '../services/api';
import { theme } from '../theme/theme';
import { getSeverityColor } from '../utils/colors';

export default function SymptomDetailScreen({ route, navigation }: any) {
  const { symptomId } = route.params;
  const [symptom, setSymptom] = useState<Symptom | null>(null);
  const [logs, setLogs] = useState<SymptomLog[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [logSeverity, setLogSeverity] = useState('2');
  const [logNotes, setLogNotes] = useState('');
  const [isSavingLog, setIsSavingLog] = useState(false);

  useEffect(() => {
    loadSymptom();
  }, [symptomId]);

  const loadSymptom = async () => {
    try {
      setIsLoading(true);
      const [data, logData] = await Promise.all([
        apiService.getSymptom(symptomId),
        apiService.getSymptomLogs(symptomId),
      ]);
      setSymptom(data);
      setLogs(logData);
    } catch (error) {
      console.error('Error loading symptom:', error);
      Alert.alert('Error', 'Failed to load symptom details');
    } finally {
      setIsLoading(false);
    }
  };

  const onRefresh = async () => {
    setRefreshing(true);
    await loadSymptom();
    setRefreshing(false);
  };

  const toggleResolved = async () => {
    if (!symptom) return;
    try {
      const updated = await apiService.updateSymptom(symptom.id, {
        is_ongoing: !symptom.is_ongoing,
      });
      setSymptom(updated);
    } catch {
      Alert.alert('Error', 'Failed to update symptom status');
    }
  };

  const confirmDelete = () => {
    Alert.alert('Delete Symptom', 'Delete this symptom record?', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Delete',
        style: 'destructive',
        onPress: async () => {
          try {
            await apiService.deleteSymptom(symptomId);
            navigation.goBack();
          } catch {
            Alert.alert('Error', 'Failed to delete symptom');
          }
        },
      },
    ]);
  };

  const addLog = async () => {
    const severity = parseInt(logSeverity, 10);
    if (!Number.isFinite(severity) || severity < 1 || severity > 4) {
      Alert.alert('Error', 'Severity must be between 1 and 4');
      return;
    }
    setIsSavingLog(true);
    try {
      const entry = await apiService.createSymptomLog(symptomId, {
        severity,
        notes: logNotes.trim() || undefined,
      });
      setLogs(prev => [entry, ...prev]);
      setLogNotes('');
    } catch {
      Alert.alert('Error', 'Failed to add symptom log');
    } finally {
      setIsSavingLog(false);
    }
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
      case 'ACUTE': return 'Acute (< 3 days)';
      case 'SUBACUTE': return 'Subacute (3-30 days)';
      case 'CHRONIC': return 'Chronic (> 30 days)';
      default: return duration;
    }
  };

  const formatDate = (dateString: string) =>
    new Date(/^\d{4}-\d{2}-\d{2}$/.test(dateString) ? `${dateString}T00:00:00` : dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    });

  if (isLoading) {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color={theme.colors.primary} />
          <Text style={styles.loadingText}>Loading symptom...</Text>
        </View>
      </SafeAreaView>
    );
  }

  if (!symptom) {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.errorContainer}>
          <Ionicons name="alert-circle" size={64} color={theme.colors.error} />
          <Title>Symptom Not Found</Title>
          <Button mode="contained" onPress={() => navigation.goBack()} style={styles.errorButton}>
            Go Back
          </Button>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.topBar}>
        <IconButton icon="arrow-left" onPress={() => navigation.goBack()} />
        <Title style={styles.topTitle}>Symptom Detail</Title>
        <IconButton icon="delete-outline" iconColor={theme.colors.error} onPress={confirmDelete} />
      </View>

      <ScrollView
        style={styles.scrollView}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
      >
        <Card style={styles.headerCard}>
          <Card.Content>
            <View style={styles.titleContainer}>
              <Title style={styles.symptomTitle}>{symptom.description}</Title>
              <View style={styles.badgesContainer}>
                <Chip
                  style={[styles.severityChip, { backgroundColor: getSeverityColor(symptom.severity) }]}
                  textStyle={styles.severityChipText}
                >
                  {getSeverityText(symptom.severity)}
                </Chip>
                <Chip
                  style={[styles.statusChip, { backgroundColor: symptom.is_ongoing ? theme.colors.error : theme.colors.primary }]}
                  textStyle={styles.statusChipText}
                >
                  {symptom.is_ongoing ? 'Active' : 'Resolved'}
                </Chip>
              </View>
            </View>

            <Divider style={styles.divider} />

            <View style={styles.detailsGrid}>
              <View style={styles.detailItem}>
                <Ionicons name="body" size={20} color={theme.colors.onSurfaceVariant} />
                <View style={styles.detailContent}>
                  <Text style={styles.detailLabel}>Body Part</Text>
                  <Text style={styles.detailValue}>{symptom.body_part || 'General'}</Text>
                </View>
              </View>
              <View style={styles.detailItem}>
                <Ionicons name="time" size={20} color={theme.colors.onSurfaceVariant} />
                <View style={styles.detailContent}>
                  <Text style={styles.detailLabel}>Duration</Text>
                  <Text style={styles.detailValue}>{getDurationText(symptom.duration)}</Text>
                </View>
              </View>
              <View style={styles.detailItem}>
                <Ionicons name="calendar" size={20} color={theme.colors.onSurfaceVariant} />
                <View style={styles.detailContent}>
                  <Text style={styles.detailLabel}>Onset Date</Text>
                  <Text style={styles.detailValue}>{formatDate(symptom.onset_date)}</Text>
                </View>
              </View>
              {symptom.end_date && (
                <View style={styles.detailItem}>
                  <Ionicons name="checkmark-circle" size={20} color={theme.colors.onSurfaceVariant} />
                  <View style={styles.detailContent}>
                    <Text style={styles.detailLabel}>Resolved Date</Text>
                    <Text style={styles.detailValue}>{formatDate(symptom.end_date)}</Text>
                  </View>
                </View>
              )}
            </View>
          </Card.Content>
        </Card>

        {symptom.notes && (
          <Card style={styles.card}>
            <Card.Content>
              <Title>Notes</Title>
              <Paragraph style={styles.notesText}>{symptom.notes}</Paragraph>
            </Card.Content>
          </Card>
        )}

        <Card style={styles.card}>
          <Card.Content>
            <Title>Symptom Logs</Title>
            <Paragraph style={styles.logHint}>Track how severity changes over time</Paragraph>

            <TextInput
              label="Log severity (1-4)"
              value={logSeverity}
              onChangeText={setLogSeverity}
              mode="outlined"
              keyboardType="number-pad"
              style={styles.logInput}
            />
            <TextInput
              label="Log notes"
              value={logNotes}
              onChangeText={setLogNotes}
              mode="outlined"
              multiline
              style={styles.logInput}
            />
            <Button mode="contained" onPress={addLog} loading={isSavingLog} disabled={isSavingLog}>
              Add Log Entry
            </Button>

            {logs.length === 0 ? (
              <Paragraph style={styles.emptyLogs}>No logs yet.</Paragraph>
            ) : (
              logs.map(log => (
                <View key={log.id} style={styles.logRow}>
                  <Chip compact style={{ backgroundColor: getSeverityColor(log.severity) }} textStyle={{ color: '#fff' }}>
                    {getSeverityText(log.severity)}
                  </Chip>
                  <View style={styles.logBody}>
                    <Text style={styles.logDate}>{formatDate(log.logged_at)}</Text>
                    {log.notes ? <Text style={styles.logNotes}>{log.notes}</Text> : null}
                  </View>
                </View>
              ))
            )}
          </Card.Content>
        </Card>

        <Card style={styles.card}>
          <Card.Content>
            <Title>Actions</Title>
            <View style={styles.actionsContainer}>
              <Button
                mode="outlined"
                onPress={() => navigation.navigate('AddSymptom', { symptomId: symptom.id })}
                icon="pencil"
                style={styles.actionButton}
              >
                Edit Symptom
              </Button>
              <Button
                mode="outlined"
                onPress={toggleResolved}
                icon={symptom.is_ongoing ? 'check' : 'refresh'}
                style={styles.actionButton}
              >
                {symptom.is_ongoing ? 'Mark Resolved' : 'Reopen'}
              </Button>
            </View>
            <Button
              mode="contained"
              onPress={() => navigation.navigate('Diagnosis')}
              icon="analytics"
              style={{ marginTop: 12 }}
            >
              Generate Diagnosis
            </Button>
          </Card.Content>
        </Card>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: theme.colors.background },
  topBar: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 4,
  },
  topTitle: { fontSize: 18, fontWeight: '600' },
  scrollView: { flex: 1 },
  loadingContainer: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  loadingText: { marginTop: 16, color: theme.colors.onSurfaceVariant },
  errorContainer: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: 32 },
  errorButton: { marginTop: 16 },
  headerCard: { margin: 16, elevation: 4 },
  titleContainer: { marginBottom: 16 },
  symptomTitle: { fontSize: 20, fontWeight: 'bold', marginBottom: 12 },
  badgesContainer: { flexDirection: 'row', gap: 8 },
  severityChip: { marginRight: 8 },
  severityChipText: { color: 'white', fontSize: 12 },
  statusChip: { marginRight: 8 },
  statusChipText: { color: 'white', fontSize: 12 },
  divider: { marginVertical: 16 },
  detailsGrid: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between' },
  detailItem: { flexDirection: 'row', alignItems: 'center', width: '48%', marginBottom: 16 },
  detailContent: { marginLeft: 12, flex: 1 },
  detailLabel: { fontSize: 12, color: theme.colors.onSurfaceVariant, marginBottom: 2 },
  detailValue: { fontSize: 14, fontWeight: '500' },
  card: { margin: 16, marginTop: 0, elevation: 2 },
  notesText: { marginTop: 8, lineHeight: 20 },
  logHint: { color: theme.colors.onSurfaceVariant, marginBottom: 12 },
  logInput: { marginBottom: 12 },
  emptyLogs: { marginTop: 16, color: theme.colors.onSurfaceVariant },
  logRow: { flexDirection: 'row', alignItems: 'flex-start', marginTop: 16, gap: 12 },
  logBody: { flex: 1 },
  logDate: { fontSize: 13, fontWeight: '600' },
  logNotes: { fontSize: 13, color: theme.colors.onSurfaceVariant, marginTop: 4 },
  actionsContainer: { flexDirection: 'row', justifyContent: 'space-around', marginTop: 16 },
  actionButton: { flex: 1, marginHorizontal: 8 },
});
