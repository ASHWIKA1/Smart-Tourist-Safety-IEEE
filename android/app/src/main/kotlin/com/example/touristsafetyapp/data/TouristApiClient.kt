package com.example.touristsafetyapp.data

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.BufferedReader
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL

data class AuthSession(
  val token: String,
  val userId: String,
  val role: String,
)

data class TouristProfile(
  val touristId: String,
  val fullName: String,
  val nationality: String,
  val passportOrIdNumber: String,
  val emergencyContactName: String,
  val emergencyContactPhone: String,
  val trackingConsent: Boolean,
  val did: String?,
)

data class TouristCredentialSummary(
  val credentialId: String,
  val did: String,
  val issuerDid: String,
  val issuanceDate: String,
  val expirationDate: String,
  val rawJson: String,
)

data class TelemetryResponse(
  val safetyStatus: String,
  val anomalyScore: Double?,
  val anomalyFlagged: Boolean,
  val activeZoneSummary: String,
  val incidentAlertId: String?,
  val incidentReason: String?,
)

data class SosResponse(
  val alertId: String,
  val priority: String,
  val status: String,
)

interface TouristGateway {
  suspend fun register(
    baseUrl: String,
    email: String,
    password: String,
    fullName: String,
    nationality: String,
    passportOrId: String,
    emergencyContactName: String,
    emergencyContactPhone: String,
  ): AuthSession

  suspend fun login(baseUrl: String, email: String, password: String): AuthSession
  suspend fun getProfile(baseUrl: String, token: String): TouristProfile
  suspend fun updateConsent(baseUrl: String, token: String, consent: Boolean): TouristProfile
  suspend fun getCredential(baseUrl: String, token: String): TouristCredentialSummary?
  suspend fun sendGps(
    baseUrl: String,
    token: String,
    lat: Double,
    lon: Double,
    accuracyM: Double,
  ): TelemetryResponse

  suspend fun triggerSos(
    baseUrl: String,
    token: String,
    lat: Double,
    lon: Double,
    note: String,
  ): SosResponse
}

class HttpTouristGateway : TouristGateway {
  override suspend fun register(
    baseUrl: String,
    email: String,
    password: String,
    fullName: String,
    nationality: String,
    passportOrId: String,
    emergencyContactName: String,
    emergencyContactPhone: String,
  ): AuthSession {
    val body = JSONObject().apply {
      put("email", email)
      put("password", password)
      put("role", "tourist")
      put("full_name", fullName)
      put("nationality", nationality)
      put("passport_or_id_number", passportOrId)
      put("emergency_contact_name", emergencyContactName)
      put("emergency_contact_phone", emergencyContactPhone)
      put("tracking_consent", false)
    }
    val res = JSONObject(request(baseUrl, "/api/v1/auth/register", "POST", null, body.toString()))
    return AuthSession(
      token = res.getString("access_token"),
      userId = res.getString("user_id"),
      role = res.getString("role"),
    )
  }

  override suspend fun login(baseUrl: String, email: String, password: String): AuthSession {
    val body = JSONObject().apply {
      put("email", email)
      put("password", password)
    }
    val res = JSONObject(request(baseUrl, "/api/v1/auth/login", "POST", null, body.toString()))
    return AuthSession(
      token = res.getString("access_token"),
      userId = res.getString("user_id"),
      role = res.getString("role"),
    )
  }

  override suspend fun getProfile(baseUrl: String, token: String): TouristProfile {
    val res = JSONObject(request(baseUrl, "/api/v1/tourists/me", "GET", token, null))
    return parseProfile(res)
  }

  override suspend fun updateConsent(
    baseUrl: String,
    token: String,
    consent: Boolean,
  ): TouristProfile {
    val body = JSONObject().put("tracking_consent", consent)
    val res = JSONObject(request(baseUrl, "/api/v1/tourists/me/consent", "PUT", token, body.toString()))
    return parseProfile(res)
  }

  override suspend fun getCredential(baseUrl: String, token: String): TouristCredentialSummary? {
    return try {
      val raw = request(baseUrl, "/api/v1/credentials/me", "GET", token, null)
      val res = JSONObject(raw)
      val subj = res.getJSONObject("credential_subject")
      TouristCredentialSummary(
        credentialId = res.getString("credential_id"),
        did = subj.getString("did"),
        issuerDid = res.getString("issuer_did"),
        issuanceDate = res.getString("issuance_date"),
        expirationDate = res.getString("expiration_date"),
        rawJson = raw,
      )
    } catch (e: ApiHttpException) {
      if (e.code == 404) null else throw e
    }
  }

  override suspend fun sendGps(
    baseUrl: String,
    token: String,
    lat: Double,
    lon: Double,
    accuracyM: Double,
  ): TelemetryResponse {
    val body = JSONObject().apply {
      put("lat", lat)
      put("lon", lon)
      put("accuracy_m", accuracyM)
    }
    val res = JSONObject(request(baseUrl, "/api/v1/telemetry/gps", "POST", token, body.toString()))
    val zones: JSONArray = res.optJSONArray("zone_evaluations") ?: JSONArray()
    val activeSummaries = mutableListOf<String>()
    for (i in 0 until zones.length()) {
      val z = zones.getJSONObject(i)
      if (z.getString("state") != "outside") {
        activeSummaries.add("${z.getString("zone_name")} (${z.getString("state")})")
      }
    }
    val incident = res.optJSONObject("incident")
    return TelemetryResponse(
      safetyStatus = res.getString("safety_status"),
      anomalyScore = if (res.isNull("anomaly_score")) null else res.getDouble("anomaly_score"),
      anomalyFlagged = res.optBoolean("anomaly_flagged", false),
      activeZoneSummary = if (activeSummaries.isEmpty()) "Outside monitored hazard zones" else activeSummaries.joinToString(", "),
      incidentAlertId = incident?.optString("alert_id"),
      incidentReason = incident?.optString("reason"),
    )
  }

  override suspend fun triggerSos(
    baseUrl: String,
    token: String,
    lat: Double,
    lon: Double,
    note: String,
  ): SosResponse {
    val body = JSONObject().apply {
      put("lat", lat)
      put("lon", lon)
      put("accuracy_m", 4.0)
      put("note", note)
    }
    val res = JSONObject(request(baseUrl, "/api/v1/sos", "POST", token, body.toString()))
    return SosResponse(
      alertId = res.getString("alert_id"),
      priority = res.getString("priority"),
      status = res.getString("status"),
    )
  }

  private fun parseProfile(res: JSONObject) = TouristProfile(
    touristId = res.getString("tourist_id"),
    fullName = res.getString("full_name"),
    nationality = res.getString("nationality"),
    passportOrIdNumber = res.getString("passport_or_id_number"),
    emergencyContactName = res.getString("emergency_contact_name"),
    emergencyContactPhone = res.getString("emergency_contact_phone"),
    trackingConsent = res.getBoolean("tracking_consent"),
    did = if (res.isNull("did")) null else res.getString("did"),
  )

  private suspend fun request(
    baseUrl: String,
    path: String,
    method: String,
    token: String?,
    jsonBody: String?,
  ): String = withContext(Dispatchers.IO) {
    val cleanBase = baseUrl.trimEnd('/')
    val conn = (URL("$cleanBase$path").openConnection() as HttpURLConnection).apply {
      requestMethod = method
      connectTimeout = 8000
      readTimeout = 8000
      setRequestProperty("Accept", "application/json")
      if (token != null) {
        setRequestProperty("Authorization", "Bearer $token")
      }
      if (jsonBody != null) {
        setRequestProperty("Content-Type", "application/json")
        doOutput = true
        OutputStreamWriter(outputStream, Charsets.UTF_8).use { it.write(jsonBody) }
      }
    }
    val code = conn.responseCode
    val stream = if (code in 200..299) conn.inputStream else conn.errorStream
    val text = stream?.bufferedReader(Charsets.UTF_8)?.use(BufferedReader::readText) ?: ""
    if (code !in 200..299) {
      throw ApiHttpException(code, text.ifBlank { "HTTP $code" })
    }
    text
  }
}

class ApiHttpException(val code: Int, message: String) : Exception(message)
