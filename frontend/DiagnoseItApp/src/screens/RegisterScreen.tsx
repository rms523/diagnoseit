import React, { useState } from 'react';
import {
  View,
  StyleSheet,
  ScrollView,
  KeyboardAvoidingView,
  Platform,
  Alert,
} from 'react-native';
import {
  TextInput,
  Button,
  Card,
  ActivityIndicator,
} from 'react-native-paper';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useAuth } from '../context/AuthContext';
import { tokens } from '../theme/tokens';
import ReferenceRangeBar from '../components/ReferenceRangeBar';
import AppText from '../components/AppText';

export default function RegisterScreen({ navigation }: any) {
  const [formData, setFormData] = useState({
    username: '',
    email: '',
    password: '',
    password_confirm: '',
    first_name: '',
    last_name: '',
  });
  const [isLoading, setIsLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const { register } = useAuth();

  const handleInputChange = (field: string, value: string) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  const validateForm = () => {
    if (!formData.username.trim()) {
      Alert.alert('Error', 'Username is required');
      return false;
    }
    if (!formData.email.trim()) {
      Alert.alert('Error', 'Email is required');
      return false;
    }
    if (!formData.password.trim()) {
      Alert.alert('Error', 'Password is required');
      return false;
    }
    if (formData.password !== formData.password_confirm) {
      Alert.alert('Error', 'Passwords do not match');
      return false;
    }
    if (formData.password.length < 6) {
      Alert.alert('Error', 'Password must be at least 6 characters');
      return false;
    }
    return true;
  };

  const handleRegister = async () => {
    if (!validateForm()) return;

    setIsLoading(true);
    try {
      const result = await register(formData);
      if (!result.success) {
        Alert.alert('Registration Failed', result.error || 'Registration failed');
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
            <AppText variant="display" style={styles.title}>Join DiagnoseIt</AppText>
            <AppText variant="body" style={styles.subtitle}>
              Start your clinical health ledger
            </AppText>
          </View>

          <Card style={styles.card} mode="elevated">
            <Card.Content>
              <AppText variant="eyebrow">Register</AppText>
              <AppText variant="title" style={styles.cardTitle}>Create account</AppText>
              <AppText variant="body" style={styles.cardSubtitle}>
                Fill in your details to get started
              </AppText>

              <View style={styles.row}>
                <TextInput
                  label="First Name"
                  value={formData.first_name}
                  onChangeText={(value) => handleInputChange('first_name', value)}
                  mode="outlined"
                  outlineColor={tokens.paperInset}
                  activeOutlineColor={tokens.teal}
                  style={[styles.input, styles.halfInput]}
                  left={<TextInput.Icon icon="account" />}
                />
                <TextInput
                  label="Last Name"
                  value={formData.last_name}
                  onChangeText={(value) => handleInputChange('last_name', value)}
                  mode="outlined"
                  outlineColor={tokens.paperInset}
                  activeOutlineColor={tokens.teal}
                  style={[styles.input, styles.halfInput]}
                />
              </View>

              <TextInput
                label="Username"
                value={formData.username}
                onChangeText={(value) => handleInputChange('username', value)}
                mode="outlined"
                outlineColor={tokens.paperInset}
                activeOutlineColor={tokens.teal}
                style={styles.input}
                autoCapitalize="none"
                autoCorrect={false}
                left={<TextInput.Icon icon="account" />}
              />

              <TextInput
                label="Email"
                value={formData.email}
                onChangeText={(value) => handleInputChange('email', value)}
                mode="outlined"
                outlineColor={tokens.paperInset}
                activeOutlineColor={tokens.teal}
                style={styles.input}
                keyboardType="email-address"
                autoCapitalize="none"
                autoCorrect={false}
                left={<TextInput.Icon icon="email" />}
              />

              <TextInput
                label="Password"
                value={formData.password}
                onChangeText={(value) => handleInputChange('password', value)}
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

              <TextInput
                label="Confirm Password"
                value={formData.password_confirm}
                onChangeText={(value) => handleInputChange('password_confirm', value)}
                mode="outlined"
                outlineColor={tokens.paperInset}
                activeOutlineColor={tokens.teal}
                style={styles.input}
                secureTextEntry={!showConfirmPassword}
                left={<TextInput.Icon icon="lock" />}
                right={
                  <TextInput.Icon
                    icon={showConfirmPassword ? 'eye-off' : 'eye'}
                    onPress={() => setShowConfirmPassword(!showConfirmPassword)}
                  />
                }
              />

              <Button
                mode="contained"
                buttonColor={tokens.teal}
                onPress={handleRegister}
                style={styles.registerButton}
                contentStyle={styles.buttonContent}
                disabled={isLoading}
              >
                {isLoading ? (
                  <ActivityIndicator color="#fff" />
                ) : (
                  'Create Account'
                )}
              </Button>

              <View style={styles.loginContainer}>
                <AppText variant="caption">Already have an account?</AppText>
                <Button
                  mode="text"
                  textColor={tokens.teal}
                  onPress={() => navigation.navigate('Login')}
                >
                  Sign in
                </Button>
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
  row: { flexDirection: 'row', justifyContent: 'space-between' },
  input: { marginBottom: 12, backgroundColor: tokens.paperElevated },
  halfInput: { flex: 1, marginHorizontal: 4 },
  registerButton: { marginTop: 8, borderRadius: tokens.radiusMd },
  buttonContent: { paddingVertical: 6 },
  loginContainer: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    marginTop: 16,
  },
});
