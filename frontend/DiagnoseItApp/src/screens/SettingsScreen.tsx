import React from 'react';
import { Alert, ScrollView, StyleSheet, View } from 'react-native';
import Constants from 'expo-constants';
import { Button, Card, Divider, List, Paragraph, Text, Title } from 'react-native-paper';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useAuth } from '../context/AuthContext';
import { theme } from '../theme/theme';

/** Only show settings that are backed by real application behavior. */
export default function SettingsScreen({ navigation }: any) {
  const { logout } = useAuth();

  const handleLogout = () => {
    Alert.alert('Logout', 'Are you sure you want to logout?', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Logout', style: 'destructive', onPress: logout },
    ]);
  };

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView style={styles.scrollView}>
        <Card style={styles.card}>
          <Card.Content>
            <Title>Account</Title>
            <Divider style={styles.divider} />
            <List.Item
              title="Profile"
              description="Update your name, contact details, and health profile"
              left={props => <List.Icon {...props} icon="account-edit" />}
              right={props => <List.Icon {...props} icon="chevron-right" />}
              onPress={() => navigation.navigate('Profile')}
            />
            <Button mode="outlined" onPress={handleLogout} icon="logout" style={styles.actionButton}>
              Logout
            </Button>
          </Card.Content>
        </Card>

        <Card style={styles.card}>
          <Card.Content>
            <Title>Privacy & data</Title>
            <Divider style={styles.divider} />
            <Paragraph style={styles.body}>
              Uploaded health documents are private to your account. Features labelled as AI may send relevant
              document text or page images to the AI service configured by your administrator. Names and contact
              details are removed from text and text-layer images; scanned images can still contain identifying details.
            </Paragraph>
            <Paragraph style={styles.body}>
              Notification, theme, unit-preference, data-export, and account-deletion controls are not yet
              available in this mobile app, so they are not shown as working settings.
            </Paragraph>
          </Card.Content>
        </Card>

        <Card style={styles.card}>
          <Card.Content>
            <Title>About</Title>
            <Divider style={styles.divider} />
            <List.Item
              title="DiagnoseIt"
              description={`Version ${Constants.expoConfig?.version || 'development'}`}
              left={props => <List.Icon {...props} icon="information" />}
            />
            <Paragraph style={styles.disclaimer}>
              DiagnoseIt helps organize health records and is not a substitute for professional medical advice.
            </Paragraph>
          </Card.Content>
        </Card>

        <View style={styles.footer}>
          <Text style={styles.footerText}>DiagnoseIt — your personal health record</Text>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: theme.colors.background },
  scrollView: { flex: 1 },
  card: { margin: 16, marginTop: 0, elevation: 2 },
  divider: { marginVertical: 16 },
  actionButton: { marginTop: 8 },
  body: { color: theme.colors.onSurfaceVariant, lineHeight: 21, marginBottom: 12 },
  disclaimer: { color: theme.colors.onSurfaceVariant, lineHeight: 20 },
  footer: { alignItems: 'center', padding: 24 },
  footerText: { fontSize: 12, color: theme.colors.onSurfaceVariant, textAlign: 'center' },
});
