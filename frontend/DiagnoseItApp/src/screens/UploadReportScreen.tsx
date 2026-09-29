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
  RadioButton,
  HelperText,
  Chip,
  IconButton,
  SegmentedButtons,
} from 'react-native-paper';
import { SafeAreaView } from 'react-native-safe-area-context';
import * as DocumentPicker from 'expo-document-picker';
import type { BulkUploadResult } from '../services/api';
import { apiService } from '../services/api';
import { theme } from '../theme/theme';

type PickedAsset = DocumentPicker.DocumentPickerAsset;
type UploadMode = 'single' | 'bulk';

const REPORT_TYPES = [
  { value: 'LAB', label: 'Laboratory Report' },
  { value: 'BLOOD', label: 'Blood Test' },
  { value: 'URINE', label: 'Urine Test' },
  { value: 'XRAY', label: 'X-Ray' },
  { value: 'MRI', label: 'MRI Scan' },
  { value: 'CT', label: 'CT Scan' },
  { value: 'OTHER', label: 'Other' },
];

function toUploadFile(asset: PickedAsset) {
  return {
    uri: asset.uri,
    name: asset.name || 'report.pdf',
    type: asset.mimeType || 'application/pdf',
  };
}

export default function UploadReportScreen({ navigation, route }: any) {
  const [mode, setMode] = useState<UploadMode>(route.params?.mode ?? 'single');
  const [formData, setFormData] = useState({
    title: '',
    report_type: 'LAB',
    lab_name: '',
    report_date: new Date().toISOString().split('T')[0],
    notes: '',
  });
  const [selectedFile, setSelectedFile] = useState<PickedAsset | null>(null);
  const [selectedFiles, setSelectedFiles] = useState<PickedAsset[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [bulkResults, setBulkResults] = useState<BulkUploadResult | null>(null);

  const switchMode = (next: UploadMode) => {
    setMode(next);
    setSelectedFile(null);
    setSelectedFiles([]);
    setBulkResults(null);
  };

  const handleInputChange = (field: string, value: string) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  const pickDocument = async () => {
    try {
      const result = await DocumentPicker.getDocumentAsync({
        type: ['application/pdf'],
        copyToCacheDirectory: true,
        multiple: mode === 'bulk',
      });

      if (result.canceled || !result.assets?.length) return;

      if (mode === 'single') {
        const asset = result.assets[0];
        setSelectedFile(asset);
        if (!formData.title.trim() && asset.name) {
          setFormData(prev => ({
            ...prev,
            title: asset.name.replace(/\.[^/.]+$/, ''),
          }));
        }
      } else {
        setSelectedFiles(prev => [...prev, ...result.assets!]);
      }
    } catch {
      Alert.alert('Error', 'Failed to pick document');
    }
  };

  const removeBulkFile = (index: number) => {
    setSelectedFiles(prev => prev.filter((_, i) => i !== index));
  };

  const validateForm = () => {
    if (mode === 'single') {
      if (!formData.title.trim()) {
        Alert.alert('Error', 'Please enter a title for the report');
        return false;
      }
      if (!selectedFile) {
        Alert.alert('Error', 'Please select a file to upload');
        return false;
      }
    } else if (selectedFiles.length === 0) {
      Alert.alert('Error', 'Select at least one file');
      return false;
    }
    return true;
  };

  const uploadReport = async () => {
    if (!validateForm()) return;

    setIsUploading(true);
    setBulkResults(null);

    try {
      if (mode === 'single' && selectedFile) {
        const report = await apiService.uploadMedicalReport(
          toUploadFile(selectedFile),
          formData.title,
          formData.report_type,
          formData.lab_name || undefined,
          formData.report_date,
          formData.notes || undefined,
        );

        Alert.alert(
          'Success',
          'Report uploaded — parsing started',
          [{
            text: 'View',
            onPress: () => navigation.replace('ReportDetail', { reportId: report.id }),
          }, {
            text: 'Done',
            onPress: () => navigation.goBack(),
          }],
        );
        return;
      }

      const result = await apiService.bulkUploadMedicalReports(
        selectedFiles.map(toUploadFile),
      );
      setBulkResults(result);
      setSelectedFiles([]);

      const msg = result.errors === 0
        ? `All ${result.created} reports uploaded`
        : `${result.created} uploaded, ${result.errors} failed`;

      Alert.alert('Bulk upload complete', msg);
    } catch (error: unknown) {
      const msg = error instanceof Error
        ? error.message.replace(/^API Error: \d+ \w+ - /, '')
        : 'Upload failed';
      Alert.alert('Error', msg);
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView style={styles.scrollView} contentContainerStyle={styles.scrollContent}>
        <View style={styles.topBar}>
          <IconButton icon="arrow-left" onPress={() => navigation.goBack()} />
          <Title style={styles.topTitle}>Upload reports</Title>
        </View>

        <SegmentedButtons
          value={mode}
          onValueChange={v => switchMode(v as UploadMode)}
          buttons={[
            { value: 'single', label: 'Single' },
            { value: 'bulk', label: 'Bulk' },
          ]}
          style={styles.modeToggle}
        />

        <Card style={styles.card}>
          <Card.Content>
            {mode === 'bulk' && (
              <Paragraph style={styles.subtitle}>
                Name files YYYY-MM-DD_lab.pdf (e.g. 2026-05-14_lalpath.pdf) to set the report date and lab automatically.
              </Paragraph>
            )}

            {mode === 'single' && (
              <>
                <TextInput
                  label="Report Title *"
                  value={formData.title}
                  onChangeText={value => handleInputChange('title', value)}
                  mode="outlined"
                  style={styles.input}
                  placeholder="e.g., Annual Blood Work 2024"
                />

                <View style={styles.section}>
                  <Text style={styles.sectionTitle}>Report Type</Text>
                  {REPORT_TYPES.map(type => (
                    <View key={type.value} style={styles.radioItem}>
                      <RadioButton
                        value={type.value}
                        status={formData.report_type === type.value ? 'checked' : 'unchecked'}
                        onPress={() => handleInputChange('report_type', type.value)}
                      />
                      <Text style={styles.radioLabel}>{type.label}</Text>
                    </View>
                  ))}
                </View>

                <TextInput
                  label="Lab/Clinic Name"
                  value={formData.lab_name}
                  onChangeText={value => handleInputChange('lab_name', value)}
                  mode="outlined"
                  style={styles.input}
                  placeholder="e.g., LabCorp"
                />

                <TextInput
                  label="Report Date"
                  value={formData.report_date}
                  onChangeText={value => handleInputChange('report_date', value)}
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
                />
              </>
            )}

            <View style={styles.fileSection}>
              <Text style={styles.sectionTitle}>
                {mode === 'bulk' ? 'Select files *' : 'Select file *'}
              </Text>
              <Button mode="outlined" onPress={pickDocument} icon="upload" style={styles.fileButton}>
                {mode === 'bulk'
                  ? selectedFiles.length > 0 ? 'Add more files' : 'Choose files'
                  : selectedFile ? 'Change file' : 'Choose file'}
              </Button>

              {mode === 'single' && selectedFile && (
                <View style={styles.fileInfo}>
                  <Text style={styles.fileName}>{selectedFile.name}</Text>
                  {selectedFile.size != null && (
                    <Text style={styles.fileSize}>
                      {(selectedFile.size / 1024 / 1024).toFixed(2)} MB
                    </Text>
                  )}
                </View>
              )}

              {mode === 'bulk' && selectedFiles.length > 0 && (
                <View style={styles.fileList}>
                  {selectedFiles.map((file, index) => (
                    <View key={`${file.uri}-${index}`} style={styles.fileListRow}>
                      <Text style={styles.fileName} numberOfLines={1}>{file.name}</Text>
                      <IconButton icon="close" size={18} onPress={() => removeBulkFile(index)} />
                    </View>
                  ))}
                </View>
              )}
            </View>

            {bulkResults && (
              <View style={styles.summary}>
                <Text style={styles.sectionTitle}>Upload summary</Text>
                <View style={styles.summaryChips}>
                  <Chip style={styles.successChip}>{bulkResults.created} created</Chip>
                  {bulkResults.errors > 0 && (
                    <Chip style={styles.errorChip}>{bulkResults.errors} failed</Chip>
                  )}
                  <Chip>{bulkResults.total} total</Chip>
                </View>
                {bulkResults.error_details.length > 0 && (
                  <View style={styles.errorList}>
                    {bulkResults.error_details.map((err, i) => (
                      <Text key={i} style={styles.errorLine}>
                        {err.file}: {err.error}
                      </Text>
                    ))}
                  </View>
                )}
              </View>
            )}

            <Button
              mode="contained"
              onPress={uploadReport}
              style={styles.uploadButton}
              contentStyle={styles.buttonContent}
              disabled={isUploading || (mode === 'bulk' ? selectedFiles.length === 0 : !selectedFile)}
            >
              {isUploading ? (
                <ActivityIndicator color="white" />
              ) : mode === 'bulk' ? (
                `Upload ${selectedFiles.length} file${selectedFiles.length !== 1 ? 's' : ''}`
              ) : (
                'Upload report'
              )}
            </Button>
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
  scrollView: { flex: 1 },
  scrollContent: { paddingBottom: 32 },
  topBar: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 8,
    paddingTop: 4,
  },
  topTitle: { fontSize: 20, flex: 1 },
  modeToggle: { marginHorizontal: 16, marginBottom: 12 },
  card: { marginHorizontal: 16, elevation: 4 },
  subtitle: {
    color: theme.colors.onSurfaceVariant,
    marginBottom: 16,
  },
  input: { marginBottom: 16 },
  section: { marginBottom: 16 },
  sectionTitle: {
    fontSize: 16,
    fontWeight: '600',
    marginBottom: 12,
    color: theme.colors.onBackground,
  },
  radioItem: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 8,
  },
  radioLabel: { marginLeft: 8, fontSize: 16 },
  fileSection: { marginBottom: 16 },
  fileButton: { marginBottom: 12 },
  fileInfo: {
    backgroundColor: theme.colors.surfaceVariant,
    padding: 12,
    borderRadius: 8,
  },
  fileList: { gap: 4 },
  fileListRow: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: theme.colors.surfaceVariant,
    borderRadius: 8,
    paddingLeft: 12,
  },
  fileName: { flex: 1, fontSize: 14, fontWeight: '500' },
  fileSize: { fontSize: 12, color: theme.colors.onSurfaceVariant, marginTop: 4 },
  summary: { marginBottom: 16 },
  summaryChips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 8 },
  successChip: { backgroundColor: theme.colors.primary },
  errorChip: { backgroundColor: theme.colors.error },
  errorList: { marginTop: 8 },
  errorLine: { fontSize: 12, color: theme.colors.error, marginBottom: 4 },
  uploadButton: { marginTop: 8, borderRadius: 8 },
  buttonContent: { paddingVertical: 8 },
});
