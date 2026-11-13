package com.example.touristsafetyapp.ui.main

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.example.touristsafetyapp.data.HttpTouristGateway
import com.example.touristsafetyapp.data.TouristCredentialSummary
import com.example.touristsafetyapp.data.TouristGateway
import com.example.touristsafetyapp.data.TouristProfile
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class TouristAppUiState(
  val serverUrl: String = "http://10.0.2.2:8000",
  val isAuthenticated: Boolean = false,
  val token: String = "",
  val isBusy: Boolean = false,
  val errorMessage: String? = null,
  val infoBanner: String? = null,
  val profile: TouristProfile? = null,
  val credential: TouristCredentialSummary? = null,
  val currentLat: Double = 11.3610,
  val currentLon: Double = 77.8280,
  val lastAccuracyM: Double = 4.0,
  val safetyStatus: String = "safe",
  val zoneSummary: String = "No GPS fix dispatched yet",
  val lastAnomalyScore: Double? = null,
  val lastSosAlertId: String? = null,
)

class MainScreenViewModel(
  private val gateway: TouristGateway = HttpTouristGateway(),
) : ViewModel() {

  private val _uiState = MutableStateFlow(TouristAppUiState())
  val uiState: StateFlow<TouristAppUiState> = _uiState.asStateFlow()

  fun updateServerUrl(url: String) {
    _uiState.update { it.copy(serverUrl = url) }
  }

  fun registerTourist(
    email: String,
    password: String,
    fullName: String,
    nationality: String,
    passportOrId: String,
    emergencyContactName: String,
    emergencyContactPhone: String,
  ) {
    viewModelScope.launch {
      _uiState.update { it.copy(isBusy = true, errorMessage = null, infoBanner = null) }
      try {
        val url = _uiState.value.serverUrl
        val session = gateway.register(
          baseUrl = url,
          email = email,
          password = password,
          fullName = fullName,
          nationality = nationality,
          passportOrId = passportOrId,
          emergencyContactName = emergencyContactName,
          emergencyContactPhone = emergencyContactPhone,
        )
        val profile = gateway.getProfile(url, session.token)
        val cred = gateway.getCredential(url, session.token)
        _uiState.update {
          it.copy(
            isAuthenticated = true,
            token = session.token,
            profile = profile,
            credential = cred,
            isBusy = false,
            infoBanner = "Registered as ${profile.fullName}. Enable GPS consent to start monitoring.",
          )
        }
      } catch (e: Exception) {
        _uiState.update { it.copy(isBusy = false, errorMessage = e.message ?: "Registration failed") }
      }
    }
  }

  fun loginTourist(email: String, password: String) {
    viewModelScope.launch {
      _uiState.update { it.copy(isBusy = true, errorMessage = null, infoBanner = null) }
      try {
        val url = _uiState.value.serverUrl
        val session = gateway.login(url, email, password)
        val profile = gateway.getProfile(url, session.token)
        val cred = gateway.getCredential(url, session.token)
        _uiState.update {
          it.copy(
            isAuthenticated = true,
            token = session.token,
            profile = profile,
            credential = cred,
            isBusy = false,
            infoBanner = "Signed in as ${profile.fullName}.",
          )
        }
      } catch (e: Exception) {
        _uiState.update { it.copy(isBusy = false, errorMessage = e.message ?: "Login failed") }
      }
    }
  }

  fun refreshCredentialAndProfile() {
    val state = _uiState.value
    if (!state.isAuthenticated) return
    viewModelScope.launch {
      _uiState.update { it.copy(isBusy = true, errorMessage = null) }
      try {
        val profile = gateway.getProfile(state.serverUrl, state.token)
        val cred = gateway.getCredential(state.serverUrl, state.token)
        _uiState.update {
          it.copy(profile = profile, credential = cred, isBusy = false)
        }
      } catch (e: Exception) {
        _uiState.update { it.copy(isBusy = false, errorMessage = e.message ?: "Refresh failed") }
      }
    }
  }

  fun toggleConsent(consent: Boolean) {
    val state = _uiState.value
    if (!state.isAuthenticated) return
    viewModelScope.launch {
      _uiState.update { it.copy(isBusy = true, errorMessage = null) }
      try {
        val updated = gateway.updateConsent(state.serverUrl, state.token, consent)
        _uiState.update {
          it.copy(
            profile = updated,
            isBusy = false,
            infoBanner = if (consent) "GPS monitoring consent enabled." else "GPS monitoring paused.",
          )
        }
      } catch (e: Exception) {
        _uiState.update { it.copy(isBusy = false, errorMessage = e.message ?: "Consent update failed") }
      }
    }
  }

  fun submitGpsObservation(lat: Double, lon: Double, accuracyM: Double = 4.0) {
    val state = _uiState.value
    if (!state.isAuthenticated) return
    if (state.profile?.trackingConsent != true) {
      _uiState.update { it.copy(errorMessage = "Enable tracking consent before sending GPS location.") }
      return
    }
    viewModelScope.launch {
      _uiState.update {
        it.copy(
          currentLat = lat,
          currentLon = lon,
          lastAccuracyM = accuracyM,
          isBusy = true,
          errorMessage = null,
        )
      }
      try {
        val res = gateway.sendGps(state.serverUrl, state.token, lat, lon, accuracyM)
        val banner = if (res.incidentAlertId != null) {
          "Alert created (${res.incidentReason}): ${res.incidentAlertId}"
        } else {
          "Location updated (${res.safetyStatus})"
        }
        _uiState.update {
          it.copy(
            isBusy = false,
            safetyStatus = res.safetyStatus,
            zoneSummary = res.activeZoneSummary,
            lastAnomalyScore = res.anomalyScore,
            infoBanner = banner,
          )
        }
      } catch (e: Exception) {
        _uiState.update { it.copy(isBusy = false, errorMessage = e.message ?: "Telemetry failed") }
      }
    }
  }

  fun triggerSos(note: String = "manual_sos_from_android") {
    val state = _uiState.value
    if (!state.isAuthenticated) return
    viewModelScope.launch {
      _uiState.update { it.copy(isBusy = true, errorMessage = null) }
      try {
        val sos = gateway.triggerSos(
          baseUrl = state.serverUrl,
          token = state.token,
          lat = state.currentLat,
          lon = state.currentLon,
          note = note,
        )
        _uiState.update {
          it.copy(
            isBusy = false,
            safetyStatus = "alert",
            lastSosAlertId = sos.alertId,
            infoBanner = "SOS sent! Alert ${sos.alertId} (${sos.priority.uppercase()}) dispatched to authorities.",
          )
        }
      } catch (e: Exception) {
        _uiState.update { it.copy(isBusy = false, errorMessage = e.message ?: "SOS failed") }
      }
    }
  }

  fun signOut() {
    _uiState.value = TouristAppUiState(serverUrl = _uiState.value.serverUrl)
  }
}
