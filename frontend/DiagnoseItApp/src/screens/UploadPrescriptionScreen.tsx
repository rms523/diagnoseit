import React, { useState } from 'react';
import { View, StyleSheet, ScrollView, Alert } from 'react-native';
import {
  Text,
  TextInput,
  Button,
  Card,
  Title,
  Paragraph,
  ActivityIndicator,
  IconButton,
} from 'react-native-paper';
import { SafeAreaView } from 'react-native-safe-area-context';
import * as DocumentPicker from 'expo-document-picker';
import { apiService } from '../services/api';
import { theme } from '../theme/theme';

type PickedAsset = DocumentPicker.DocumentPickerAsset;

export default function UploadPrescriptionScreen({ navigation }: any) {
  const [formData, setFormData] = useState({
    doctor_name: '',
    hospital_clinic: '',
    prescription_date: new Date().toISOString().split('T')[0],
    notes: '',
  });
  const [selectedFile, setSelectedFile] = useState<PickedAsset | null>(null);
  const [isUploading, setIsUploading] = useState(false);

  const handleInputChange = (field: string, value: string) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  const pickDocument = async () => {
    try {
      const result = await DocumentPicker.getDocumentAsync({
        type: ['application/pdf'],
        copyToCacheDirectory: true,
      });

      if (result.canceled || !result.assets?.length) return;
      setSelectedFile(result.assets[0]);
    } catch {
      Alert.alert('Error', 'Failed to pick document');
    }
  };

  const validateForm = () => {
    if (!selectedFile) {
      Alert.alert('Error', 'Please select a prescription file');
      return false;
    }
    return true;
  };

  const uploadPrescription = async () => {
    if (!validateForm() || !selectedFile) return;

    setIsUploading(true);
    try {
      await apiService.uploadPrescription(
        {
          uri: selectedFile.uri,
          name: selectedFile.name || 'prescription.pdf',
          type: selectedFile.mimeType || 'application/pdf',
        },
        formData.doctor_name.trim() || undefined,
        formData.hospital_clinic.trim() || undefined,
        formData.prescription_date,
        formData.notes.trim() || undefined,
      );

      Alert.alert('Success', 'Prescription uploaded successfully', [
        { text: 'OK', onPress: () => navigation.goBack() },
      ]);
    } catch (error: any) {
      Alert.alert('Error', error.message || 'Failed to upload prescription');
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.topBar}>
        <IconButton icon="arrow-left" onPress={() => navigation.goBack()} />
        <Title style={styles.topTitle}>Upload Prescription</Title>
        <View style={{ width: 48 }} />
      </View>

      <ScrollView contentContainerStyle={styles.content}>
        <Card style={styles.card}>
          <Card.Content>
            <Paragraph style={styles.subtitle}>
              Upload a PDF or image of your prescription
            </Paragraph>

            <Button mode="outlined" onPress={pickDocument} icon="file-upload" style={styles.pickButton}>
              {selectedFile ? selectedFile.name : 'Select File'}
            </Button>

            <TextInput
              label="Doctor Name"
              value={formData.doctor_name}
              onChangeText={value => handleInputChange('doctor_name', value)}
              mode="outlined"
              style={styles.input}
              placeholder="Dr. Smith"
            />

            <TextInput
              label="Hospital / Clinic"
              value={formData.hospital_clinic}
              onChangeText={value => handleInputChange('hospital_clinic', value)}
              mode="outlined"
              style={styles.input}
              placeholder="Hospital or clinic name"
            />

            <TextInput
              label="Prescription Date"
              value={formData.prescription_date}
              onChangeText={value => handleInputChange('prescription_date', value)}
              mode="outlined"
              style={styles.input}
              placeholder="YYYY-MM-DD"
            />

            <TextInput
              label="Notes"
              value={formData.notes}
              onChangeText={value => handleInputChange('notes', value)}
              mode="outlined"
              style={styles.input}
              multiline
              numberOfLines={3}
              placeholder="Any additional notes…"
            />

            <Button
              mode="contained"
              onPress={uploadPrescription}
              disabled={isUploading}
              style={styles.submitButton}
              contentStyle={styles.buttonContent}
            >
              {isUploading ? <ActivityIndicator color="white" /> : 'Upload Prescription'}
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
  content: { padding: 16, paddingBottom: 32 },
  card: { elevation: 2 },
  subtitle: { color: theme.colors.onSurfaceVariant, marginBottom: 16 },
  pickButton: { marginBottom: 16 },
  input: { marginBottom: 12 },
  submitButton: { marginTop: 8, borderRadius: 8 },
  buttonContent: { paddingVertical: 8 },
});
