import React, { useEffect, useState } from 'react';
import {
  View,
  StyleSheet,
  ScrollView,
  Alert,
} from 'react-native';
import {
  Text,
  TextInput,
  Button,
  Card,
  Title,
  Paragraph,
  ActivityIndicator,
  SegmentedButtons,
  HelperText,
  IconButton,
} from 'react-native-paper';
import { SafeAreaView } from 'react-native-safe-area-context';
import { apiService } from '../services/api';
import { theme } from '../theme/theme';

const SEVERITY_LEVELS = [
  { value: 1, label: 'Mild' },
  { value: 2, label: 'Moderate' },
  { value: 3, label: 'Severe' },
  { value: 4, label: 'Critical' },
];

const DURATION_TYPES = [
  { value: 'ACUTE', label: 'Acute (< 3 days)' },
  { value: 'SUBACUTE', label: 'Subacute (3-30 days)' },
  { value: 'CHRONIC', label: 'Chronic (> 30 days)' },
];

const BODY_PARTS = [
  'Head', 'Neck', 'Chest', 'Back', 'Abdomen', 'Arms', 'Legs',
  'Hands', 'Feet', 'General', 'Other',
];

export default function AddSymptomScreen({ navigation, route }: any) {
  const symptomId = route.params?.symptomId as number | undefined;
  const isEditing = Boolean(symptomId);

  const [formData, setFormData] = useState({
    description: '',
    severity: 1,
    duration: 'ACUTE',
    body_part: '',
    onset_date: new Date().toISOString().split('T')[0],
    notes: '',
  });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isLoading, setIsLoading] = useState(isEditing);

  useEffect(() => {
    if (!symptomId) return;
    const load = async () => {
      try {
        const symptom = await apiService.getSymptom(symptomId);
        setFormData({
          description: symptom.description,
          severity: symptom.severity,
          duration: symptom.duration,
          body_part: symptom.body_part || '',
          onset_date: symptom.onset_date.split('T')[0],
          notes: symptom.notes || '',
        });
      } catch {
        Alert.alert('Error', 'Failed to load symptom');
        navigation.goBack();
      } finally {
        setIsLoading(false);
      }
    };
    load();
  }, [symptomId, navigation]);

  const handleInputChange = (field: string, value: string | number) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  const validateForm = () => {
    if (!formData.description.trim()) {
      Alert.alert('Error', 'Please describe your symptom');
      return false;
    }
    if (!formData.body_part.trim()) {
      Alert.alert('Error', 'Please select a body part');
      return false;
    }
    return true;
  };

  const submitSymptom = async () => {
    if (!validateForm()) return;

    setIsSubmitting(true);
    try {
      const payload = {
        description: formData.description.trim(),
        severity: formData.severity as 1 | 2 | 3 | 4,
        duration: formData.duration as 'ACUTE' | 'SUBACUTE' | 'CHRONIC',
        body_part: formData.body_part,
        onset_date: formData.onset_date,
        notes: formData.notes.trim() || undefined,
      };

      if (isEditing && symptomId) {
        await apiService.updateSymptom(symptomId, payload);
      } else {
        await apiService.createSymptom(payload);
      }

      Alert.alert(
        'Success',
        isEditing ? 'Symptom updated successfully!' : 'Symptom recorded successfully!',
        [{ text: 'OK', onPress: () => navigation.goBack() }],
      );
    } catch (error: any) {
      Alert.alert('Error', error.message || 'Failed to save symptom');
    } finally {
      setIsSubmitting(false);
    }
  };

  if (isLoading) {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color={theme.colors.primary} />
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.topBar}>
        <IconButton icon="arrow-left" onPress={() => navigation.goBack()} />
        <Title style={styles.topTitle}>{isEditing ? 'Edit Symptom' : 'Record Symptom'}</Title>
        <View style={{ width: 48 }} />
      </View>

      <ScrollView style={styles.scrollView}>
        <Card style={styles.card}>
          <Card.Content>
            <Paragraph style={styles.subtitle}>
              {isEditing
                ? 'Update symptom details and severity'
                : 'Track your symptoms to help with diagnosis and treatment'}
            </Paragraph>

            <TextInput
              label="Symptom Description *"
              value={formData.description}
              onChangeText={value => handleInputChange('description', value)}
              mode="outlined"
              style={styles.input}
              multiline
              numberOfLines={3}
              placeholder="Describe your symptom in detail..."
            />

            <View style={styles.section}>
              <Text style={styles.sectionTitle}>Severity Level *</Text>
              <SegmentedButtons
                value={formData.severity.toString()}
                onValueChange={value => handleInputChange('severity', parseInt(value, 10))}
                buttons={SEVERITY_LEVELS.map(level => ({
                  value: level.value.toString(),
                  label: level.label,
                }))}
                style={styles.segmentedButtons}
              />
            </View>

            <View style={styles.section}>
              <Text style={styles.sectionTitle}>Duration *</Text>
              <SegmentedButtons
                value={formData.duration}
                onValueChange={value => handleInputChange('duration', value)}
                buttons={DURATION_TYPES}
                style={styles.segmentedButtons}
              />
            </View>

            <View style={styles.section}>
              <Text style={styles.sectionTitle}>Body Part *</Text>
              <View style={styles.bodyPartsGrid}>
                {BODY_PARTS.map(part => (
                  <Button
                    key={part}
                    mode={formData.body_part === part ? 'contained' : 'outlined'}
                    onPress={() => handleInputChange('body_part', part)}
                    style={styles.bodyPartButton}
                    compact
                  >
                    {part}
                  </Button>
                ))}
              </View>
            </View>

            <TextInput
              label="Onset Date *"
              value={formData.onset_date}
              onChangeText={value => handleInputChange('onset_date', value)}
              mode="outlined"
              style={styles.input}
              placeholder="YYYY-MM-DD"
            />
            <HelperText type="info">When did you first notice this symptom?</HelperText>

            <TextInput
              label="Additional Notes"
              value={formData.notes}
              onChangeText={value => handleInputChange('notes', value)}
              mode="outlined"
              style={styles.input}
              multiline
              numberOfLines={3}
              placeholder="Any additional details about this symptom..."
            />

            <Button
              mode="contained"
              onPress={submitSymptom}
              style={styles.submitButton}
              contentStyle={styles.buttonContent}
              disabled={isSubmitting}
            >
              {isSubmitting ? (
                <ActivityIndicator color="white" />
              ) : (
                isEditing ? 'Save Changes' : 'Record Symptom'
              )}
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
  loadingContainer: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  scrollView: { flex: 1 },
  card: { margin: 16, elevation: 4 },
  subtitle: { color: theme.colors.onSurfaceVariant, marginBottom: 24 },
  input: { marginBottom: 16 },
  section: { marginBottom: 24 },
  sectionTitle: {
    fontSize: 16,
    fontWeight: '600',
    marginBottom: 12,
    color: theme.colors.onBackground,
  },
  segmentedButtons: { marginBottom: 8 },
  bodyPartsGrid: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between' },
  bodyPartButton: { width: '30%', marginBottom: 8 },
  submitButton: { marginTop: 16, borderRadius: 8 },
  buttonContent: { paddingVertical: 8 },
});
