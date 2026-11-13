package com.example.touristsafetyapp.ui.main

import com.example.touristsafetyapp.data.AuthSession
import com.example.touristsafetyapp.data.SosResponse
import com.example.touristsafetyapp.data.TelemetryResponse
import com.example.touristsafetyapp.data.TouristCredentialSummary
import com.example.touristsafetyapp.data.TouristGateway
import com.example.touristsafetyapp.data.TouristProfile
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class MainScreenViewModelTest {
  private val dispatcher = StandardTestDispatcher()

  @Before
  fun setUp() {
    Dispatchers.setMain(dispatcher)
  }

  @After
  fun tearDown() {
    Dispatchers.resetMain()
  }

  @Test
  fun login_consent_gps_and_sos_workflow() = runTest {
    val vm = MainScreenViewModel(FakeTouristGateway())
    vm.loginTourist("ajay@example.com", "secret123")
    advanceUntilIdle()

    assertTrue(vm.uiState.value.isAuthenticated)
    assertEquals("Ajay K", vm.uiState.value.profile?.fullName)

    vm.toggleConsent(true)
    advanceUntilIdle()
    assertTrue(vm.uiState.value.profile?.trackingConsent == true)

    vm.submitGpsObservation(11.3652, 77.8342, 3.5)
    advanceUntilIdle()
    assertEquals("alert", vm.uiState.value.safetyStatus)

    vm.triggerSos("sos_test")
    advanceUntilIdle()
    assertEquals("alert-sos-1", vm.uiState.value.lastSosAlertId)
  }
}

private class FakeTouristGateway : TouristGateway {
  private var consent = false

  override suspend fun register(
    baseUrl: String,
    email: String,
    password: String,
    fullName: String,
    nationality: String,
    passportOrId: String,
    emergencyContactName: String,
    emergencyContactPhone: String,
  ) = AuthSession("tok-1", "usr-1", "tourist")

  override suspend fun login(baseUrl: String, email: String, password: String) =
    AuthSession("tok-1", "usr-1", "tourist")

  override suspend fun getProfile(baseUrl: String, token: String) = TouristProfile(
    touristId = "usr-1",
    fullName = "Ajay K",
    nationality = "IN",
    passportOrIdNumber = "P123",
    emergencyContactName = "Geetha",
    emergencyContactPhone = "+91-9876543210",
    trackingConsent = consent,
    did = "did:tourist:abc",
  )

  override suspend fun updateConsent(baseUrl: String, token: String, consent: Boolean): TouristProfile {
    this.consent = consent
    return getProfile(baseUrl, token)
  }

  override suspend fun getCredential(baseUrl: String, token: String) = TouristCredentialSummary(
    credentialId = "vc:tourist:1",
    did = "did:tourist:abc",
    issuerDid = "did:tourist:authority:in-tn-01",
    issuanceDate = "2026-11-12T00:00:00Z",
    expirationDate = "2026-12-12T00:00:00Z",
    rawJson = "{}",
  )

  override suspend fun sendGps(
    baseUrl: String,
    token: String,
    lat: Double,
    lon: Double,
    accuracyM: Double,
  ) = TelemetryResponse(
    safetyStatus = "alert",
    anomalyScore = 0.72,
    anomalyFlagged = false,
    activeZoneSummary = "Cliff Hazard Area (inside)",
    incidentAlertId = "alert-zone-1",
    incidentReason = "restricted_zone_entry",
  )

  override suspend fun triggerSos(
    baseUrl: String,
    token: String,
    lat: Double,
    lon: Double,
    note: String,
  ) = SosResponse("alert-sos-1", "critical", "pending")
}
