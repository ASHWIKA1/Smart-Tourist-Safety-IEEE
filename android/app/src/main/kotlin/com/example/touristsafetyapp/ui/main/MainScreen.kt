package com.example.touristsafetyapp.ui.main

import android.Manifest
import android.annotation.SuppressLint
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.location.LocationManager
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CenterAlignedTopAppBar
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation3.runtime.NavKey
import com.example.touristsafetyapp.R
import com.example.touristsafetyapp.data.TouristCredentialSummary
import com.example.touristsafetyapp.data.TouristProfile
import com.example.touristsafetyapp.ui.theme.TouristSafetyAppTheme

@Composable
fun MainScreen(
  onItemClick: (NavKey) -> Unit,
  modifier: Modifier = Modifier,
  viewModel: MainScreenViewModel = viewModel { MainScreenViewModel() },
) {
  val uiState by viewModel.uiState.collectAsStateWithLifecycle()
  val context = LocalContext.current

  val permissionLauncher = rememberLauncherForActivityResult(
    contract = ActivityResultContracts.RequestMultiplePermissions()
  ) { grants ->
    val granted = grants[Manifest.permission.ACCESS_FINE_LOCATION] == true ||
      grants[Manifest.permission.ACCESS_COARSE_LOCATION] == true
    if (granted) {
      readLastKnownLocation(context)?.let { (lat, lon, acc) ->
        viewModel.submitGpsObservation(lat, lon, acc)
      }
    }
  }

  TouristSafetyAppContent(
    state = uiState,
    modifier = modifier,
    onServerUrlChange = viewModel::updateServerUrl,
    onLogin = viewModel::loginTourist,
    onRegister = viewModel::registerTourist,
    onToggleConsent = viewModel::toggleConsent,
    onRefresh = viewModel::refreshCredentialAndProfile,
    onSendDeviceGps = {
      val hasFine = ContextCompat.checkSelfPermission(
        context, Manifest.permission.ACCESS_FINE_LOCATION
      ) == PackageManager.PERMISSION_GRANTED
      if (!hasFine) {
        permissionLauncher.launch(
          arrayOf(
            Manifest.permission.ACCESS_FINE_LOCATION,
            Manifest.permission.ACCESS_COARSE_LOCATION,
          )
        )
      } else {
        val fix = readLastKnownLocation(context)
        if (fix != null) {
          viewModel.submitGpsObservation(fix.first, fix.second, fix.third)
        } else {
          viewModel.submitGpsObservation(uiState.currentLat, uiState.currentLon, 4.0)
        }
      }
    },
    onSendCoordinates = viewModel::submitGpsObservation,
    onTriggerSos = { viewModel.triggerSos("manual_sos_from_android") },
    onDialEmergency = { phone ->
      val intent = Intent(Intent.ACTION_DIAL, Uri.parse("tel:$phone"))
      context.startActivity(intent)
    },
    onSignOut = viewModel::signOut,
  )
}

@SuppressLint("MissingPermission")
private fun readLastKnownLocation(context: Context): Triple<Double, Double, Double>? {
  val lm = context.getSystemService(Context.LOCATION_SERVICE) as? LocationManager ?: return null
  val gps = lm.getLastKnownLocation(LocationManager.GPS_PROVIDER)
  val net = lm.getLastKnownLocation(LocationManager.NETWORK_PROVIDER)
  val best = gps ?: net ?: return null
  return Triple(best.latitude, best.longitude, best.accuracy.toDouble().coerceAtLeast(2.0))
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun TouristSafetyAppContent(
  state: TouristAppUiState,
  modifier: Modifier = Modifier,
  onServerUrlChange: (String) -> Unit = {},
  onLogin: (String, String) -> Unit = { _, _ -> },
  onRegister: (String, String, String, String, String, String, String) -> Unit = { _, _, _, _, _, _, _ -> },
  onToggleConsent: (Boolean) -> Unit = {},
  onRefresh: () -> Unit = {},
  onSendDeviceGps: () -> Unit = {},
  onSendCoordinates: (Double, Double, Double) -> Unit = { _, _, _ -> },
  onTriggerSos: () -> Unit = {},
  onDialEmergency: (String) -> Unit = {},
  onSignOut: () -> Unit = {},
) {
  Scaffold(
    modifier = modifier,
    topBar = {
      CenterAlignedTopAppBar(
        title = { Text(stringResource(R.string.app_name)) },
        colors = TopAppBarDefaults.topAppBarColors(
          containerColor = MaterialTheme.colorScheme.primaryContainer,
          titleContentColor = MaterialTheme.colorScheme.primary,
        ),
      )
    },
  ) { innerPadding ->
    Column(
      modifier = Modifier
        .padding(innerPadding)
        .fillMaxSize()
        .verticalScroll(rememberScrollState())
        .padding(16.dp),
      verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
      state.errorMessage?.let { err ->
        Card(colors = CardDefaults.cardColors(containerColor = Color(0xFFFEE2E2))) {
          Text(
            text = err,
            color = Color(0xFF991B1B),
            modifier = Modifier.padding(12.dp),
          )
        }
      }
      state.infoBanner?.let { info ->
        Card(colors = CardDefaults.cardColors(containerColor = Color(0xFFDCFCE7))) {
          Text(
            text = info,
            color = Color(0xFF166534),
            modifier = Modifier.padding(12.dp),
          )
        }
      }

      if (!state.isAuthenticated) {
        AuthCard(
          serverUrl = state.serverUrl,
          isBusy = state.isBusy,
          onServerUrlChange = onServerUrlChange,
          onLogin = onLogin,
          onRegister = onRegister,
        )
      } else {
        SafetyStatusCard(state = state)

        SosButtonCard(
          isBusy = state.isBusy,
          lastSosAlertId = state.lastSosAlertId,
          onTriggerSos = onTriggerSos,
        )

        GpsTrackingCard(
          consentEnabled = state.profile?.trackingConsent == true,
          currentLat = state.currentLat,
          currentLon = state.currentLon,
          onToggleConsent = onToggleConsent,
          onSendDeviceGps = onSendDeviceGps,
          onSimulateRestrictedEntry = {
            // Restricted cliff zone center from backend default geography
            onSendCoordinates(11.365227, 77.834229, 3.5)
          },
          onSimulateSafePoint = {
            onSendCoordinates(11.362349, 77.830748, 3.5)
          },
        )

        DigitalIdentityCard(
          did = state.profile?.did,
          credential = state.credential,
          onRefresh = onRefresh,
        )

        state.profile?.let { prof ->
          EmergencyContactCard(
            profile = prof,
            onDialEmergency = onDialEmergency,
          )
        }

        OutlinedButton(
          onClick = onSignOut,
          modifier = Modifier.fillMaxWidth(),
        ) {
          Text("Sign Out")
        }
      }
    }
  }
}

@Composable
private fun AuthCard(
  serverUrl: String,
  isBusy: Boolean,
  onServerUrlChange: (String) -> Unit,
  onLogin: (String, String) -> Unit,
  onRegister: (String, String, String, String, String, String, String) -> Unit,
) {
  var isRegisterMode by remember { mutableStateOf(false) }
  var email by remember { mutableStateOf("tourist@safety.local") }
  var password by remember { mutableStateOf("Tourist123!") }
  var fullName by remember { mutableStateOf("Ajay K") }
  var nationality by remember { mutableStateOf("IN") }
  var passportOrId by remember { mutableStateOf("P99887766") }
  var emergencyName by remember { mutableStateOf("Dr. B. G. Geetha") }
  var emergencyPhone by remember { mutableStateOf("+91-9876543210") }

  Card(modifier = Modifier.fillMaxWidth()) {
    Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
      Text(
        text = if (isRegisterMode) "Tourist Registration" else "Tourist Sign In",
        style = MaterialTheme.typography.titleMedium,
        fontWeight = FontWeight.Bold,
      )
      OutlinedTextField(
        value = serverUrl,
        onValueChange = onServerUrlChange,
        label = { Text("Backend URL") },
        modifier = Modifier.fillMaxWidth(),
        singleLine = true,
      )
      OutlinedTextField(
        value = email,
        onValueChange = { email = it },
        label = { Text("Email") },
        modifier = Modifier.fillMaxWidth(),
        singleLine = true,
      )
      OutlinedTextField(
        value = password,
        onValueChange = { password = it },
        label = { Text("Password") },
        visualTransformation = PasswordVisualTransformation(),
        modifier = Modifier.fillMaxWidth(),
        singleLine = true,
      )

      if (isRegisterMode) {
        OutlinedTextField(
          value = fullName,
          onValueChange = { fullName = it },
          label = { Text("Full Name") },
          modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(
          value = nationality,
          onValueChange = { nationality = it },
          label = { Text("Nationality") },
          modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(
          value = passportOrId,
          onValueChange = { passportOrId = it },
          label = { Text("Passport / ID Number") },
          modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(
          value = emergencyName,
          onValueChange = { emergencyName = it },
          label = { Text("Emergency Contact Name") },
          modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(
          value = emergencyPhone,
          onValueChange = { emergencyPhone = it },
          label = { Text("Emergency Contact Phone") },
          modifier = Modifier.fillMaxWidth(),
        )
      }

      Button(
        onClick = {
          if (isRegisterMode) {
            onRegister(email, password, fullName, nationality, passportOrId, emergencyName, emergencyPhone)
          } else {
            onLogin(email, password)
          }
        },
        enabled = !isBusy,
        modifier = Modifier.fillMaxWidth(),
      ) {
        Text(if (isRegisterMode) "Register Tourist Account" else "Sign In")
      }

      OutlinedButton(
        onClick = { isRegisterMode = !isRegisterMode },
        modifier = Modifier.fillMaxWidth(),
      ) {
        Text(if (isRegisterMode) "Already registered? Sign In" else "New tourist? Register")
      }
    }
  }
}

@Composable
private fun SafetyStatusCard(state: TouristAppUiState) {
  val bg = when (state.safetyStatus) {
    "alert" -> Color(0xFFFEE2E2)
    "caution" -> Color(0xFFFEF3C7)
    else -> Color(0xFFDCFCE7)
  }
  val fg = when (state.safetyStatus) {
    "alert" -> Color(0xFF991B1B)
    "caution" -> Color(0xFF92400E)
    else -> Color(0xFF166534)
  }

  Card(
    modifier = Modifier.fillMaxWidth(),
    colors = CardDefaults.cardColors(containerColor = bg),
  ) {
    Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
      Text(
        text = "SAFETY STATUS: ${state.safetyStatus.uppercase()}",
        color = fg,
        fontWeight = FontWeight.Bold,
        style = MaterialTheme.typography.titleMedium,
      )
      Text(text = state.zoneSummary, color = fg)
      Text(
        text = "Last Fix: ${"%.5f".format(state.currentLat)}, ${"%.5f".format(state.currentLon)} (±${state.lastAccuracyM} m)",
        color = fg,
        style = MaterialTheme.typography.bodySmall,
      )
      state.lastAnomalyScore?.let { score ->
        Text(
          text = "AI Anomaly Score: ${"%.4f".format(score)}",
          color = fg,
          style = MaterialTheme.typography.bodySmall,
        )
      }
    }
  }
}

@Composable
private fun SosButtonCard(
  isBusy: Boolean,
  lastSosAlertId: String?,
  onTriggerSos: () -> Unit,
) {
  Card(modifier = Modifier.fillMaxWidth()) {
    Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
      Text(
        text = "Emergency Assistance",
        style = MaterialTheme.typography.titleMedium,
        fontWeight = FontWeight.Bold,
      )
      Button(
        onClick = onTriggerSos,
        enabled = !isBusy,
        colors = ButtonDefaults.buttonColors(containerColor = Color(0xFFDC2626)),
        modifier = Modifier
          .fillMaxWidth()
          .height(56.dp),
      ) {
        Text("SEND SOS EMERGENCY ALERT", fontWeight = FontWeight.Bold)
      }
      lastSosAlertId?.let { id ->
        Text("Last SOS Alert ID: $id", style = MaterialTheme.typography.bodySmall)
      }
    }
  }
}

@Composable
private fun GpsTrackingCard(
  consentEnabled: Boolean,
  currentLat: Double,
  currentLon: Double,
  onToggleConsent: (Boolean) -> Unit,
  onSendDeviceGps: () -> Unit,
  onSimulateRestrictedEntry: () -> Unit,
  onSimulateSafePoint: () -> Unit,
) {
  Card(modifier = Modifier.fillMaxWidth()) {
    Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
      Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
      ) {
        Column(modifier = Modifier.weight(1f)) {
          Text("GPS Location Tracking Consent", fontWeight = FontWeight.Bold)
          Text(
            text = if (consentEnabled) "Sharing enabled for active trip" else "Paused (off)",
            style = MaterialTheme.typography.bodySmall,
          )
        }
        Switch(checked = consentEnabled, onCheckedChange = onToggleConsent)
      }

      Text(
        text = "Current coordinates: ${"%.5f".format(currentLat)}, ${"%.5f".format(currentLon)}",
        style = MaterialTheme.typography.bodySmall,
      )

      Button(
        onClick = onSendDeviceGps,
        enabled = consentEnabled,
        modifier = Modifier.fillMaxWidth(),
      ) {
        Text("Send Live Device GPS Fix")
      }

      Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
        OutlinedButton(
          onClick = onSimulateSafePoint,
          enabled = consentEnabled,
          modifier = Modifier.weight(1f),
        ) {
          Text("Test Safe Zone")
        }
        OutlinedButton(
          onClick = onSimulateRestrictedEntry,
          enabled = consentEnabled,
          modifier = Modifier.weight(1f),
        ) {
          Text("Test Restricted")
        }
      }
    }
  }
}

@Composable
private fun DigitalIdentityCard(
  did: String?,
  credential: TouristCredentialSummary?,
  onRefresh: () -> Unit,
) {
  Card(modifier = Modifier.fillMaxWidth()) {
    Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
      Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
      ) {
        Text("Digital Identity Wallet", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
        OutlinedButton(onClick = onRefresh) { Text("Sync") }
      }
      if (credential == null) {
        Text("DID: ${did ?: "Pending authority issuance"}")
        Text(
          "An authorized tourism verifier must issue your signed Verifiable Credential.",
          style = MaterialTheme.typography.bodySmall,
        )
      } else {
        Text("DID: ${credential.did}", style = MaterialTheme.typography.bodySmall)
        Text("Credential ID: ${credential.credentialId}", style = MaterialTheme.typography.bodySmall)
        Text("Issuer: ${credential.issuerDid}", style = MaterialTheme.typography.bodySmall)
        Text("Expires: ${credential.expirationDate}", style = MaterialTheme.typography.bodySmall)
      }
    }
  }
}

@Composable
private fun EmergencyContactCard(
  profile: TouristProfile,
  onDialEmergency: (String) -> Unit,
) {
  Card(modifier = Modifier.fillMaxWidth()) {
    Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
      Text("Emergency Contact", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
      Text("${profile.emergencyContactName} (${profile.emergencyContactPhone})")
      Spacer(modifier = Modifier.height(4.dp))
      OutlinedButton(
        onClick = { onDialEmergency(profile.emergencyContactPhone) },
        modifier = Modifier.fillMaxWidth(),
      ) {
        Text("Call Emergency Contact")
      }
    }
  }
}

@Preview(showBackground = true, showSystemUi = true)
@Composable
fun MainScreenPreview() {
  TouristSafetyAppTheme {
    TouristSafetyAppContent(
      state = TouristAppUiState(
        isAuthenticated = true,
        profile = TouristProfile(
          touristId = "usr-demo",
          fullName = "Ajay K",
          nationality = "IN",
          passportOrIdNumber = "P99887766",
          emergencyContactName = "Dr. B. G. Geetha",
          emergencyContactPhone = "+91-9876543210",
          trackingConsent = true,
          did = "did:tourist:demo1234",
        ),
        safetyStatus = "safe",
        zoneSummary = "Heritage Plaza (inside)",
      )
    )
  }
}
