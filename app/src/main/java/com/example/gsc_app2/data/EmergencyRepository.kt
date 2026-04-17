package com.example.gsc_app2.data



import com.example.gsc_app2.model.EmergencyResponse
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow

class EmergencyRepository(private val wsClient: WebSocketClient) {

    val emergencyInstructions: SharedFlow<EmergencyResponse> = wsClient.responses
    val connectionState: StateFlow<WebSocketClient.ConnectionState> = wsClient.connectionState

    fun connect() = wsClient.connect()
    fun disconnect() = wsClient.disconnect()
    fun sendCameraFrame(jpegBytes: ByteArray) = wsClient.sendFrame(jpegBytes)
}