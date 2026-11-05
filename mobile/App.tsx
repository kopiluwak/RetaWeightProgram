// App shell and hand-rolled navigator. There is no navigation library on
// purpose (small screen count): Root switches on auth state first
// (signed out -> email/OTP; not onboarded -> onboarding) and then on a simple
// `screen` union for the authenticated app, passing callbacks as navigation.
import React, { useState } from "react";
import { ActivityIndicator, StyleSheet, View } from "react-native";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { StatusBar } from "expo-status-bar";
import { AuthProvider, useAuth } from "./src/AuthContext";
import { BillingProvider, shouldGate, useBilling } from "./src/BillingContext";
import { NavContext } from "./src/NavContext";
import { InventoryVersion, Program } from "./src/api";
import { useTheme } from "./src/theme";
import EmailEntryScreen from "./src/screens/EmailEntryScreen";
import OtpEntryScreen from "./src/screens/OtpEntryScreen";
import OnboardingScreen from "./src/screens/OnboardingScreen";
import PendingDeletionScreen from "./src/screens/PendingDeletionScreen";
import PaywallScreen from "./src/screens/PaywallScreen";
import HomeScreen from "./src/screens/HomeScreen";
import CaptureScreen from "./src/screens/CaptureScreen";
import ConfirmInventoryScreen from "./src/screens/ConfirmInventoryScreen";
import ProgramScreen from "./src/screens/ProgramScreen";
import CouchProgramScreen from "./src/screens/CouchProgramScreen";
import CustomizationScreen from "./src/screens/CustomizationScreen";
import AddExerciseScreen from "./src/screens/AddExerciseScreen";
import WorkoutScreen from "./src/screens/WorkoutScreen";
import ProgressScreen from "./src/screens/ProgressScreen";
import ExerciseTrendsScreen from "./src/screens/ExerciseTrendsScreen";
import HistoryScreen from "./src/screens/HistoryScreen";
import NutritionHomeScreen from "./src/screens/NutritionHomeScreen";
import NutritionSetupScreen from "./src/screens/NutritionSetupScreen";
import KitchenScanScreen from "./src/screens/KitchenScanScreen";
import RecipesScreen from "./src/screens/RecipesScreen";
import ProteinTrackerScreen from "./src/screens/ProteinTrackerScreen";
import ProteinBoostersScreen from "./src/screens/ProteinBoostersScreen";
import VoiceLogScreen from "./src/screens/VoiceLogScreen";
import { NutritionApi } from "./src/api";
import { TabBar } from "./src/ui";
import type { TabKey } from "./src/ui";

type AuthStep = "email" | "otp";
type AppScreen =
  | "home" | "capture" | "confirm" | "program" | "customization" | "addExercise" | "workout" | "progress" | "trends" | "history"
  | "nutrition" | "nutritionSetup" | "kitchenScan" | "recipes" | "tracker" | "boosters" | "voiceLog";

/** Top-level router: picks the visible screen from auth + local nav state. */
function Root() {
  const { loading, me, refreshMe, signOut, clearSession } = useAuth();
  // Billing: `paywall` is set reactively by the 402 interceptor in api.ts, and
  // proactively by the FIRST-SCAN gate (PAYWALL_GATE in BillingContext).
  const { paywall, hidePaywall, status: billing } = useBilling();
  const [step, setStep] = useState<AuthStep>("email");
  const [pendingEmail, setPendingEmail] = useState("");
  const [screen, setScreen] = useState<AppScreen>("home");
  const [draft, setDraft] = useState<InventoryVersion | null>(null);
  const [workoutCtx, setWorkoutCtx] = useState<{ program: Program; dayIndex: number } | null>(null);
  const [trendsExercise, setTrendsExercise] = useState<string | null>(null);
  const [nutritionFirstRun, setNutritionFirstRun] = useState(false);
  const [recipesAutoGen, setRecipesAutoGen] = useState(false);
  const [forceFullProgram, setForceFullProgram] = useState(false);
  const [captureMode, setCaptureMode] = useState<"replace" | "add">("replace");
  const [addExerciseProgram, setAddExerciseProgram] = useState<Program | null>(null);
  const theme = useTheme();

  // Neutron entry: first use asks for weight -> protein target; after that,
  // straight to the nutrition dashboard.
  async function openNutrition() {
    try {
      const p = await NutritionApi.profile();
      setNutritionFirstRun(!p.onboarded);
      setScreen(p.onboarded ? "nutrition" : "nutritionSetup");
    } catch {
      setNutritionFirstRun(false);
      setScreen("nutrition");
    }
  }

  if (loading) {
    return (
      <View style={[styles.center, { backgroundColor: theme.colors.background }]}>
        <ActivityIndicator size="large" color={theme.colors.text} />
      </View>
    );
  }

  // Signed out -> auth flow
  if (!me) {
    if (step === "email") {
      return (
        <EmailEntryScreen
          onCodeSent={(email) => {
            setPendingEmail(email);
            setStep("otp");
          }}
        />
      );
    }
    return (
      <OtpEntryScreen
        email={pendingEmail}
        onVerified={refreshMe}
        onBack={() => setStep("email")}
      />
    );
  }

  // Signed in but pending deletion -> restore gate (App Store 5.1.1(v)).
  // Checked BEFORE onboarding so a half-onboarded account can still be
  // restored or left alone, and so no screen that writes data is reachable
  // while the account is scheduled to be destroyed.
  if (me.deletion_requested_at) {
    return (
      <PendingDeletionScreen
        me={me}
        onRestored={refreshMe}
        onSignOut={signOut}
      />
    );
  }

  // Signed in but not onboarded -> onboarding
  if (!me.habits?.onboarded) {
    return <OnboardingScreen onDone={refreshMe} />;
  }

  // Fully set up — authenticated app screens. The whole area is wrapped in a
  // NavContext so ScreenBackground renders a persistent Home control everywhere.
  const goHome = () => {
    setWorkoutCtx(null);
    setDraft(null);
    setForceFullProgram(false);
    setScreen("home");
    refreshMe();
  };

  // The paywall supersedes whatever screen is underneath. Two ways in:
  //   * the gate — the user reached PAYWALL_GATE ("capture") with no scans left.
  //     Closing goes Home, because returning to capture would just re-gate.
  //   * a 402 from anywhere — closing returns to the screen they were on.
  const gated = shouldGate(screen, billing);
  const showPaywall = gated || paywall !== null;

  const content = ((): React.ReactNode => {
  if (showPaywall) {
    return (
      <PaywallScreen
        onClose={() => {
          hidePaywall();
          if (gated) goHome();
        }}
      />
    );
  }
  if (screen === "capture") {
    return (
      <CaptureScreen
        mode={captureMode}
        onCancel={() => setScreen(captureMode === "add" ? "program" : "home")}
        onRecognized={(d) => {
          setDraft(d);
          setScreen("confirm");
        }}
      />
    );
  }
  if (screen === "confirm" && draft) {
    const returnTo = captureMode === "add" ? "program" : "home";
    return (
      <ConfirmInventoryScreen
        draft={draft}
        onConfirmed={() => {
          setDraft(null);
          setCaptureMode("replace");
          setScreen(returnTo);
        }}
        onBack={() => {
          setDraft(null);
          setScreen("capture");
        }}
      />
    );
  }
  if (screen === "customization") {
    return (
      <CustomizationScreen
        onDone={() => setScreen("program")}
        onBack={() => setScreen("program")}
      />
    );
  }
  if (screen === "addExercise" && addExerciseProgram) {
    return (
      <AddExerciseScreen
        program={addExerciseProgram}
        onDone={() => setScreen("program")}
        onBack={() => setScreen("program")}
      />
    );
  }
  if (screen === "program") {
    const couch = me.habits?.couch;
    const showCouch = !!couch?.mode && !couch?.graduated && !forceFullProgram;
    const openWorkout = (program: Program, dayIndex: number) => {
      setWorkoutCtx({ program, dayIndex });
      setScreen("workout");
    };
    const openAddEquipment = () => {
      setCaptureMode("add");
      setScreen("capture");
    };
    const openAddExercise = (program: Program) => {
      setAddExerciseProgram(program);
      setScreen("addExercise");
    };
    if (showCouch) {
      return (
        <CouchProgramScreen
          onBack={() => {
            refreshMe();
            setScreen("home");
          }}
          onStartWorkout={openWorkout}
          onGraduate={() => {
            setForceFullProgram(true);
            refreshMe();
          }}
          onCustomize={() => setScreen("customization")}
          onAddEquipment={openAddEquipment}
          onAddExercise={openAddExercise}
          onStateChanged={refreshMe}
          habitDays={me.habits?.days_per_week}
        />
      );
    }
    return (
      <ProgramScreen
        onBack={() => setScreen("home")}
        onStartWorkout={openWorkout}
        onCustomize={() => setScreen("customization")}
        onAddEquipment={openAddEquipment}
        onAddExercise={openAddExercise}
        onModeChanged={() => {
          setForceFullProgram(false);
          refreshMe();
        }}
      />
    );
  }
  if (screen === "progress") {
    return (
      <ProgressScreen
        onBack={() => setScreen("home")}
        onOpenTrends={() => {
          setTrendsExercise(null);
          setScreen("trends");
        }}
        onOpenHistory={() => setScreen("history")}
        onOpenExercise={(name) => {
          setTrendsExercise(name);
          setScreen("trends");
        }}
      />
    );
  }
  if (screen === "trends") {
    return <ExerciseTrendsScreen onBack={() => setScreen("progress")} initialExercise={trendsExercise} />;
  }
  if (screen === "history") {
    return <HistoryScreen onBack={() => setScreen("progress")} />;
  }
  if (screen === "nutrition") {
    return (
      <NutritionHomeScreen
        onBack={() => setScreen("home")}
        onScanKitchen={() => setScreen("kitchenScan")}
        onRecipes={() => {
          setRecipesAutoGen(false);
          setScreen("recipes");
        }}
        onTracker={() => setScreen("tracker")}
        onBoosters={() => setScreen("boosters")}
        onVoiceLog={() => setScreen("voiceLog")}
        onEditProfile={() => {
          setNutritionFirstRun(false);
          setScreen("nutritionSetup");
        }}
      />
    );
  }
  if (screen === "nutritionSetup") {
    return (
      <NutritionSetupScreen
        firstRun={nutritionFirstRun}
        onDone={() => setScreen("nutrition")}
        onBack={() => setScreen(nutritionFirstRun ? "home" : "nutrition")}
      />
    );
  }
  if (screen === "kitchenScan") {
    return (
      <KitchenScanScreen
        onCancel={() => setScreen("nutrition")}
        onSaved={(generateNow) => {
          if (generateNow) {
            setRecipesAutoGen(true);
            setScreen("recipes");
          } else {
            setScreen("nutrition");
          }
        }}
      />
    );
  }
  if (screen === "recipes") {
    return <RecipesScreen onBack={() => setScreen("nutrition")} autoGenerate={recipesAutoGen} />;
  }
  if (screen === "tracker") {
    return <ProteinTrackerScreen onBack={() => setScreen("nutrition")} />;
  }
  if (screen === "voiceLog") {
    return <VoiceLogScreen onBack={() => setScreen("nutrition")} />;
  }
  if (screen === "boosters") {
    return <ProteinBoostersScreen onBack={() => setScreen("nutrition")} />;
  }
  if (screen === "workout" && workoutCtx) {
    return (
      <WorkoutScreen
        program={workoutCtx.program}
        dayIndex={workoutCtx.dayIndex}
        onDone={() => {
          setWorkoutCtx(null);
          setScreen("program");
        }}
      />
    );
  }
  return (
    <HomeScreen
      me={me}
      onScan={() => {
        setCaptureMode("replace");
        setScreen("capture");
      }}
      onViewProgram={() => setScreen("program")}
      onViewProgress={() => setScreen("progress")}
      onNutrition={openNutrition}
      onSignOut={signOut}
      onAccountDeleted={clearSession}
    />
  );
  })();

  // Persistent bottom tabs on the four top-level destinations only. Focused
  // flows (capture, workout, sub-screens) hide the bar and use a back control.
  const TAB_SCREENS: Record<string, TabKey> = {
    home: "home",
    program: "program",
    progress: "progress",
    nutrition: "nutrition",
  };
  // No tab bar over the paywall — it's a focused flow, like capture or workout.
  const currentTab = showPaywall ? undefined : TAB_SCREENS[screen];
  const selectTab = (key: TabKey) => {
    if (key === "home") return goHome();
    if (key === "nutrition") return openNutrition();
    setScreen(key);
  };

  return (
    <NavContext.Provider value={{ goHome }}>
      <View style={styles.flex}>
        <View style={styles.flex}>{content}</View>
        {currentTab ? <TabBar current={currentTab} onSelect={selectTab} /> : null}
      </View>
    </NavContext.Provider>
  );
}

/** App root: providers (safe area, auth) wrapped around the router. */
export default function App() {
  return (
    <SafeAreaProvider>
      <AuthProvider>
        {/* Inside AuthProvider: the RevenueCat App User ID is the backend
            users.id, so billing can't configure until we know who is signed in. */}
        <BillingProvider>
          <StatusBar style="auto" />
          <Root />
        </BillingProvider>
      </AuthProvider>
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
  flex: { flex: 1 },
});
