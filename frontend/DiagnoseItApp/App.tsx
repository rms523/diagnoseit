import React, { useEffect } from 'react';
import { StyleSheet } from 'react-native';
import { NavigationContainer, DefaultTheme } from '@react-navigation/native';
import { createStackNavigator } from '@react-navigation/stack';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { createDrawerNavigator } from '@react-navigation/drawer';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { Provider as PaperProvider } from 'react-native-paper';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import * as SplashScreen from 'expo-splash-screen';
import {
  useFonts,
  Literata_400Regular,
  Literata_600SemiBold,
} from '@expo-google-fonts/literata';
import {
  IBMPlexSans_400Regular,
  IBMPlexSans_500Medium,
  IBMPlexSans_600SemiBold,
} from '@expo-google-fonts/ibm-plex-sans';
import { IBMPlexMono_400Regular } from '@expo-google-fonts/ibm-plex-mono';
import { Ionicons } from '@expo/vector-icons';

// Screens
import LoginScreen from './src/screens/LoginScreen';
import RegisterScreen from './src/screens/RegisterScreen';
import DashboardScreen from './src/screens/DashboardScreen';
import MedicalReportsScreen from './src/screens/MedicalReportsScreen';
import ReportDetailScreen from './src/screens/ReportDetailScreen';
import UploadReportScreen from './src/screens/UploadReportScreen';
import UploadPrescriptionScreen from './src/screens/UploadPrescriptionScreen';
import SymptomsScreen from './src/screens/SymptomsScreen';
import SymptomDetailScreen from './src/screens/SymptomDetailScreen';
import AddSymptomScreen from './src/screens/AddSymptomScreen';
import DiagnosisScreen from './src/screens/DiagnosisScreen';
import DiagnosisDetailScreen from './src/screens/DiagnosisDetailScreen';
import PrescriptionsScreen from './src/screens/PrescriptionsScreen';
import PrescriptionDetailScreen from './src/screens/PrescriptionDetailScreen';
import ProfileScreen from './src/screens/ProfileScreen';
import SettingsScreen from './src/screens/SettingsScreen';
import HealthTrendsScreen from './src/screens/HealthTrendsScreen';
import UnitConverterScreen from './src/screens/UnitConverterScreen';

// Context
import { AuthProvider, useAuth } from './src/context/AuthContext';
import { navigationTheme, theme } from './src/theme/theme';
import { tokens } from './src/theme/tokens';

SplashScreen.preventAutoHideAsync();

const navTheme = {
  ...DefaultTheme,
  colors: { ...DefaultTheme.colors, ...navigationTheme.colors },
};

const Stack = createStackNavigator();
const Tab = createBottomTabNavigator();
const Drawer = createDrawerNavigator();

// Main Tab Navigator
function MainTabs() {
  return (
    <Tab.Navigator
      screenOptions={({ route }) => ({
        tabBarIcon: ({ focused, color, size }) => {
          let iconName: keyof typeof Ionicons.glyphMap;

          if (route.name === 'Dashboard') {
            iconName = focused ? 'home' : 'home-outline';
          } else if (route.name === 'Reports') {
            iconName = focused ? 'document-text' : 'document-text-outline';
          } else if (route.name === 'Symptoms') {
            iconName = focused ? 'medical' : 'medical-outline';
          } else if (route.name === 'Diagnosis') {
            iconName = focused ? 'analytics' : 'analytics-outline';
          } else if (route.name === 'Prescriptions') {
            iconName = focused ? 'receipt' : 'receipt-outline';
          } else {
            iconName = 'help-outline';
          }

          return <Ionicons name={iconName} size={size} color={color} />;
        },
        tabBarActiveTintColor: tokens.teal,
        tabBarInactiveTintColor: tokens.inkMuted,
        tabBarStyle: {
          backgroundColor: tokens.paperElevated,
          borderTopColor: tokens.paperInset,
        },
        headerShown: false,
      })}
    >
      <Tab.Screen name="Dashboard" component={DashboardScreen} />
      <Tab.Screen name="Reports" component={MedicalReportsScreen} />
      <Tab.Screen name="Symptoms" component={SymptomsScreen} />
      <Tab.Screen name="Diagnosis" component={DiagnosisScreen} />
      <Tab.Screen name="Prescriptions" component={PrescriptionsScreen} />
    </Tab.Navigator>
  );
}

// Drawer Navigator
function MainDrawer() {
  return (
    <Drawer.Navigator
      screenOptions={{
        headerShown: false,
        drawerActiveTintColor: tokens.teal,
        drawerInactiveTintColor: tokens.inkMuted,
        drawerStyle: { backgroundColor: tokens.paperElevated },
      }}
    >
      <Drawer.Screen 
        name="MainTabs" 
        component={MainTabs}
        options={{ title: 'DiagnoseIt' }}
      />
      <Drawer.Screen 
        name="HealthTrends" 
        component={HealthTrendsScreen}
        options={{
          title: 'Health Trends',
          drawerIcon: ({ color, size }) => (
            <Ionicons name="analytics-outline" size={size} color={color} />
          ),
        }}
      />
      <Drawer.Screen 
        name="UnitConverter" 
        component={UnitConverterScreen}
        options={{
          title: 'Unit Converter',
          drawerIcon: ({ color, size }) => (
            <Ionicons name="swap-horizontal-outline" size={size} color={color} />
          ),
        }}
      />
      <Drawer.Screen 
        name="Profile" 
        component={ProfileScreen}
        options={{
          drawerIcon: ({ color, size }) => (
            <Ionicons name="person-outline" size={size} color={color} />
          ),
        }}
      />
      <Drawer.Screen 
        name="Settings" 
        component={SettingsScreen}
        options={{
          drawerIcon: ({ color, size }) => (
            <Ionicons name="settings-outline" size={size} color={color} />
          ),
        }}
      />
    </Drawer.Navigator>
  );
}

// Auth Stack
function AuthStack() {
  return (
    <Stack.Navigator screenOptions={{ headerShown: false }}>
      <Stack.Screen name="Login" component={LoginScreen} />
      <Stack.Screen name="Register" component={RegisterScreen} />
    </Stack.Navigator>
  );
}

// Main App Navigator
function AppNavigator() {
  const { isAuthenticated, isLoading } = useAuth();

  if (isLoading) {
    return null; // You can add a loading screen here
  }

  return (
    <NavigationContainer theme={navTheme}>
      {isAuthenticated ? (
        <Stack.Navigator screenOptions={{ headerShown: false }}>
          <Stack.Screen name="MainDrawer" component={MainDrawer} />
          <Stack.Screen name="ReportDetail" component={ReportDetailScreen} />
          <Stack.Screen name="UploadReport" component={UploadReportScreen} />
          <Stack.Screen name="UploadPrescription" component={UploadPrescriptionScreen} />
          <Stack.Screen name="SymptomDetail" component={SymptomDetailScreen} />
          <Stack.Screen name="AddSymptom" component={AddSymptomScreen} />
          <Stack.Screen name="DiagnosisDetail" component={DiagnosisDetailScreen} />
          <Stack.Screen name="PrescriptionDetail" component={PrescriptionDetailScreen} />
        </Stack.Navigator>
      ) : (
        <AuthStack />
      )}
    </NavigationContainer>
  );
}

// Main App Component
export default function App() {
  const [fontsLoaded] = useFonts({
    Literata_400Regular,
    Literata_600SemiBold,
    IBMPlexSans_400Regular,
    IBMPlexSans_500Medium,
    IBMPlexSans_600SemiBold,
    IBMPlexMono_400Regular,
  });

  useEffect(() => {
    if (fontsLoaded) {
      SplashScreen.hideAsync();
    }
  }, [fontsLoaded]);

  if (!fontsLoaded) {
    return null;
  }

  return (
    <GestureHandlerRootView style={styles.root}>
      <SafeAreaProvider>
        <PaperProvider theme={theme}>
          <AuthProvider>
            <AppNavigator />
            <StatusBar style="dark" />
          </AuthProvider>
        </PaperProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
});