import React from 'react';
import { View, StyleSheet } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import {
  Text,
  TextInput,
  Button,
  Card,
  ActivityIndicator,
} from 'react-native-paper';
import { KeyboardAvoidingView, Platform, ScrollView, Alert } from 'react-native';
import { useAuth } from '../context/AuthContext';
import { apiService } from '../services/api';
import { theme } from '../theme/theme';
import { tokens } from '../theme/tokens';
import ReferenceRangeBar from '../components/ReferenceRangeBar';
import AppText from '../components/AppText';

export default function LoginScreen({ navigation }: any) {
  const [username, setUsername] = React.useState('');
  const [password, setPassword] = React.useState('');
  const [isLoading, setIsLoading] = React.useState(false);
  const [showPassword, setShowPassword] = React.useState(false);
  const { login } = useAuth();
  // Sign-up is offered only while the server accepts new accounts; a failed check leaves it on offer.
  const [registrationOpen, setRegistrationOpen] = React.useState(true);

  React.useEffect(() => {
    let active = true;
    apiService
      .getRegistrationStatus()
      .then(status => { if (active) setRegistrationOpen(status.open); })
      .catch(() => {});
    return () => { active = false; };
  }, []);

  const handleLogin = async () => {
    if (!username.trim() || !password.trim()) {
      Alert.alert('Error', 'Please fill in all fields');
      return;
    }

    setIsLoading(true);
    try {
      const result = await login(username.trim(), password);
      if (!result.success) {
        Alert.alert('Login Failed', result.error || 'Invalid credentials');
      }
    } catch {
      Alert.alert('Error', 'An unexpected error occurred');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <SafeAreaView style={styles.container}>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        style={styles.keyboardView}
      >
        <ScrollView contentContainerStyle={styles.scrollContent}>
          <View style={styles.header}>
            <View style={styles.logoMark}>
              <AppText variant="display" style={styles.logoLetter}>D</AppText>
            </View>
            <ReferenceRangeBar width={160} />
            <AppText variant="display" style={styles.title}>DiagnoseIt</AppText>
            <AppText variant="body" style={styles.subtitle}>
              Clinical health ledger
            </AppText>
          </View>

          <Card style={styles.card} mode="elevated">
            <Card.Content>
              <AppText variant="eyebrow">Sign in</AppText>
              <AppText variant="title" style={styles.cardTitle}>Welcome back</AppText>
              <AppText variant="body" style={styles.cardSubtitle}>
                Access your reports, symptoms, and trends
              </AppText>

              <TextInput
                label="Username"
                value={username}
                onChangeText={setUsername}
                mode="outlined"
                outlineColor={tokens.paperInset}
                activeOutlineColor={tokens.teal}
                style={styles.input}
                autoCapitalize="none"
                autoCorrect={false}
                left={<TextInput.Icon icon="account" />}
              />

              <TextInput
                label="Password"
                value={password}
                onChangeText={setPassword}
                mode="outlined"
                outlineColor={tokens.paperInset}
                activeOutlineColor={tokens.teal}
                style={styles.input}
                secureTextEntry={!showPassword}
                left={<TextInput.Icon icon="lock" />}
                right={
                  <TextInput.Icon
                    icon={showPassword ? 'eye-off' : 'eye'}
                    onPress={() => setShowPassword(!showPassword)}
                  />
                }
              />

              <Button
                mode="contained"
                buttonColor={tokens.teal}
                onPress={handleLogin}
                style={styles.loginButton}
                contentStyle={styles.buttonContent}
                disabled={isLoading}
              >
                {isLoading ? <ActivityIndicator color="#fff" /> : 'Sign in'}
              </Button>

              <View style={styles.registerContainer}>
                {registrationOpen ? (
                  <>
                    <AppText variant="caption">No account?</AppText>
                    <Button
                      mode="text"
                      textColor={tokens.teal}
                      onPress={() => navigation.navigate('Register')}
                    >
                      Create one
                    </Button>
                  </>
                ) : (
                  <AppText variant="caption">Need an account? Ask this server's administrator.</AppText>
                )}
              </View>
            </Card.Content>
          </Card>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: tokens.paper },
  keyboardView: { flex: 1 },
  scrollContent: { flexGrow: 1, justifyContent: 'center', padding: 20 },
  header: { alignItems: 'center', marginBottom: 32, gap: 10 },
  logoMark: {
    width: 56,
    height: 56,
    borderRadius: tokens.radiusLg,
    backgroundColor: tokens.teal,
    alignItems: 'center',
    justifyContent: 'center',
  },
  logoLetter: { color: tokens.paperElevated, fontSize: 28 },
  title: { marginTop: 4 },
  subtitle: { textAlign: 'center' },
  card: {
    backgroundColor: tokens.paperElevated,
    borderRadius: tokens.radiusLg,
    borderWidth: 1,
    borderColor: tokens.paperInset,
  },
  cardTitle: { marginTop: 8, marginBottom: 4 },
  cardSubtitle: { marginBottom: 20 },
  input: { marginBottom: 12, backgroundColor: tokens.paperElevated },
  loginButton: { marginTop: 8, borderRadius: tokens.radiusMd },
  buttonContent: { paddingVertical: 6 },
  registerContainer: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    marginTop: 16,
  },
});
