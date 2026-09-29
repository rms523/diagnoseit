import React, { useEffect, useState } from 'react';
import {
  View,
  StyleSheet,
  ScrollView,
  Alert,
} from 'react-native';
import {
  Text,
  Card,
  Title,
  Paragraph,
  Button,
  TextInput,
  ActivityIndicator,
  Avatar,
  Divider,
} from 'react-native-paper';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useAuth } from '../context/AuthContext';
import { apiService, User } from '../services/api';
import { theme } from '../theme/theme';

type GenderOption = 'M' | 'F' | 'O';

type ProfileFormData = {
  first_name: string;
  last_name: string;
  email: string;
  phone_number: string;
  emergency_contact: string;
  emergency_phone: string;
  date_of_birth: string;
  gender: GenderOption | '';
};

function formatOptionalDate(value?: string): string {
  if (!value) return 'Not available';
  const localValue = /^\d{4}-\d{2}-\d{2}$/.test(value) ? `${value}T00:00:00` : value;
  return new Date(localValue).toLocaleDateString();
}

export default function ProfileScreen({ navigation }: any) {
  const { user, updateUser, logout } = useAuth();
  const [isEditing, setIsEditing] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [formData, setFormData] = useState<ProfileFormData>({
    first_name: '',
    last_name: '',
    email: '',
    phone_number: '',
    emergency_contact: '',
    emergency_phone: '',
    date_of_birth: '',
    gender: '',
  });

  useEffect(() => {
    if (user) {
      setFormData({
        first_name: user.first_name || '',
        last_name: user.last_name || '',
        email: user.email || '',
        phone_number: user.phone_number || '',
        emergency_contact: user.emergency_contact || '',
        emergency_phone: user.emergency_phone || '',
        date_of_birth: user.date_of_birth || '',
        gender: user.gender || '',
      });
    }
  }, [user]);

  const handleInputChange = (field: string, value: string) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  const handleSave = async () => {
    try {
      setIsLoading(true);
      const payload: Partial<User> = {
        first_name: formData.first_name,
        last_name: formData.last_name,
        email: formData.email,
        phone_number: formData.phone_number,
        emergency_contact: formData.emergency_contact,
        emergency_phone: formData.emergency_phone,
        date_of_birth: formData.date_of_birth || undefined,
        gender: formData.gender || undefined,
      };
      await updateUser(payload);
      setIsEditing(false);
      Alert.alert('Success', 'Profile updated successfully');
    } catch (error) {
      console.error('Error updating profile:', error);
      Alert.alert('Error', 'Failed to update profile');
    } finally {
      setIsLoading(false);
    }
  };

  const handleLogout = () => {
    Alert.alert(
      'Logout',
      'Are you sure you want to logout?',
      [
        { text: 'Cancel', style: 'cancel' },
        { 
          text: 'Logout', 
          style: 'destructive',
          onPress: logout
        },
      ]
    );
  };

  const getInitials = () => {
    const first = formData.first_name?.charAt(0) || '';
    const last = formData.last_name?.charAt(0) || '';
    return (first + last).toUpperCase() || user?.username?.charAt(0).toUpperCase() || 'U';
  };

  const getGenderText = (gender: string) => {
    switch (gender) {
      case 'M': return 'Male';
      case 'F': return 'Female';
      case 'O': return 'Other';
      default: return 'Not specified';
    }
  };

  if (!user) {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color={theme.colors.primary} />
          <Text style={styles.loadingText}>Loading profile...</Text>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView style={styles.scrollView}>
        {/* Header Card */}
        <Card style={styles.headerCard}>
          <Card.Content style={styles.headerContent}>
            <Avatar.Text 
              size={80} 
              label={getInitials()}
              style={styles.avatar}
            />
            <View style={styles.userInfo}>
              <Title style={styles.userName}>
                {formData.first_name && formData.last_name 
                  ? `${formData.first_name} ${formData.last_name}`
                  : user.username
                }
              </Title>
              <Text style={styles.userEmail}>{user.email}</Text>
              <Text style={styles.memberSince}>
                Member since {formatOptionalDate(user.created_at)}
              </Text>
            </View>
            <Button
              mode="outlined"
              onPress={() => setIsEditing(!isEditing)}
              icon={isEditing ? "close" : "pencil"}
              compact
            >
              {isEditing ? 'Cancel' : 'Edit'}
            </Button>
          </Card.Content>
        </Card>

        {/* Personal Information */}
        <Card style={styles.card}>
          <Card.Content>
            <Title>Personal Information</Title>
            <Divider style={styles.divider} />
            
            <View style={styles.inputRow}>
              <TextInput
                label="First Name"
                value={formData.first_name}
                onChangeText={(value) => handleInputChange('first_name', value)}
                mode="outlined"
                style={styles.halfInput}
                editable={isEditing}
              />
              <TextInput
                label="Last Name"
                value={formData.last_name}
                onChangeText={(value) => handleInputChange('last_name', value)}
                mode="outlined"
                style={styles.halfInput}
                editable={isEditing}
              />
            </View>

            <TextInput
              label="Email"
              value={formData.email}
              onChangeText={(value) => handleInputChange('email', value)}
              mode="outlined"
              style={styles.input}
              keyboardType="email-address"
              autoCapitalize="none"
              editable={isEditing}
            />

            <TextInput
              label="Phone Number"
              value={formData.phone_number}
              onChangeText={(value) => handleInputChange('phone_number', value)}
              mode="outlined"
              style={styles.input}
              keyboardType="phone-pad"
              editable={isEditing}
            />

            <View style={styles.inputRow}>
              <TextInput
                label="Date of Birth"
                value={formData.date_of_birth}
                onChangeText={(value) => handleInputChange('date_of_birth', value)}
                mode="outlined"
                style={styles.halfInput}
                placeholder="YYYY-MM-DD"
                editable={isEditing}
              />
              <TextInput
                label="Gender"
                value={formData.gender}
                onChangeText={(value) => handleInputChange('gender', value)}
                mode="outlined"
                style={styles.halfInput}
                placeholder="M/F/O"
                editable={isEditing}
              />
            </View>
          </Card.Content>
        </Card>

        {/* Emergency Contact */}
        <Card style={styles.card}>
          <Card.Content>
            <Title>Emergency Contact</Title>
            <Divider style={styles.divider} />
            
            <TextInput
              label="Emergency Contact Name"
              value={formData.emergency_contact}
              onChangeText={(value) => handleInputChange('emergency_contact', value)}
              mode="outlined"
              style={styles.input}
              editable={isEditing}
            />

            <TextInput
              label="Emergency Contact Phone"
              value={formData.emergency_phone}
              onChangeText={(value) => handleInputChange('emergency_phone', value)}
              mode="outlined"
              style={styles.input}
              keyboardType="phone-pad"
              editable={isEditing}
            />
          </Card.Content>
        </Card>

        {/* Account Information */}
        <Card style={styles.card}>
          <Card.Content>
            <Title>Account Information</Title>
            <Divider style={styles.divider} />
            
            <View style={styles.infoRow}>
              <Text style={styles.infoLabel}>Username</Text>
              <Text style={styles.infoValue}>{user.username}</Text>
            </View>
            
            <View style={styles.infoRow}>
              <Text style={styles.infoLabel}>User ID</Text>
              <Text style={styles.infoValue}>{user.id}</Text>
            </View>
            
            <View style={styles.infoRow}>
              <Text style={styles.infoLabel}>Account Created</Text>
              <Text style={styles.infoValue}>
                {formatOptionalDate(user.created_at)}
              </Text>
            </View>
            
            <View style={styles.infoRow}>
              <Text style={styles.infoLabel}>Last Updated</Text>
              <Text style={styles.infoValue}>
                {formatOptionalDate(user.updated_at)}
              </Text>
            </View>
          </Card.Content>
        </Card>

        {/* Actions */}
        {isEditing && (
          <Card style={styles.card}>
            <Card.Content>
              <Button
                mode="contained"
                onPress={handleSave}
                style={styles.saveButton}
                contentStyle={styles.buttonContent}
                disabled={isLoading}
              >
                {isLoading ? (
                  <ActivityIndicator color="white" />
                ) : (
                  'Save Changes'
                )}
              </Button>
            </Card.Content>
          </Card>
        )}

        <Card style={styles.card}>
          <Card.Content>
            <Button
              mode="outlined"
              onPress={() => navigation.navigate('Settings')}
              icon="settings"
              style={styles.actionButton}
            >
              Settings
            </Button>
            
            <Button
              mode="outlined"
              onPress={handleLogout}
              icon="logout"
              style={[styles.actionButton, styles.logoutButton]}
              textColor={theme.colors.error}
            >
              Logout
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
  headerCard: {
    margin: 16,
    elevation: 4,
  },
  headerContent: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  avatar: {
    marginRight: 16,
    backgroundColor: theme.colors.primary,
  },
  userInfo: {
    flex: 1,
  },
  userName: {
    fontSize: 20,
    fontWeight: 'bold',
    marginBottom: 4,
  },
  userEmail: {
    fontSize: 14,
    color: theme.colors.onSurfaceVariant,
    marginBottom: 4,
  },
  memberSince: {
    fontSize: 12,
    color: theme.colors.onSurfaceVariant,
  },
  card: {
    margin: 16,
    marginTop: 0,
    elevation: 2,
  },
  divider: {
    marginVertical: 16,
  },
  inputRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  input: {
    marginBottom: 16,
  },
  halfInput: {
    flex: 1,
    marginHorizontal: 4,
    marginBottom: 16,
  },
  infoRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 8,
  },
  infoLabel: {
    fontSize: 14,
    color: theme.colors.onSurfaceVariant,
  },
  infoValue: {
    fontSize: 14,
    fontWeight: '500',
  },
  saveButton: {
    marginTop: 16,
    borderRadius: 8,
  },
  buttonContent: {
    paddingVertical: 8,
  },
  actionButton: {
    marginBottom: 8,
  },
  logoutButton: {
    borderColor: theme.colors.error,
  },
});
