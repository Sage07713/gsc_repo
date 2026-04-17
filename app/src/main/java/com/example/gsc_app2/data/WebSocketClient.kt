package com.example.gsc_app2.data

import android.util.Base64
import com.example.gsc_app2.model.EmergencyResponse
import com.google.gson.Gson
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import java.util.concurrent.TimeUnit

class WebSocketClient(private val serverUrl: String) {

    private val client = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(0, TimeUnit.MILLISECONDS)
        .build()

    private var webSocket: WebSocket? = null

    private val _responses = MutableSharedFlow<EmergencyResponse>()
    val responses: SharedFlow<EmergencyResponse> = _responses.asSharedFlow()

    private val _connectionState = MutableStateFlow(ConnectionState.DISCONNECTED)
    val connectionState: StateFlow<ConnectionState> = _connectionState.asStateFlow()

    enum class ConnectionState { DISCONNECTED, CONNECTING, CONNECTED, ERROR }

    fun connect() {
        _connectionState.value = ConnectionState.CONNECTING
        val request = Request.Builder().url(serverUrl).build()
        webSocket = client.newWebSocket(request, object : WebSocketListener() {

            override fun onOpen(webSocket: WebSocket, response: Response) {
                _connectionState.value = ConnectionState.CONNECTED
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                runCatching {
                    Gson().fromJson(text, EmergencyResponse::class.java)
                }.onSuccess { response ->
                    CoroutineScope(Dispatchers.IO).launch {
                        _responses.emit(response)
                    }
                }
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                _connectionState.value = ConnectionState.ERROR
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                _connectionState.value = ConnectionState.DISCONNECTED
            }
        })
    }

    fun sendFrame(jpegBytes: ByteArray) {
        if (_connectionState.value != ConnectionState.CONNECTED) return
        val base64 = Base64.encodeToString(jpegBytes, Base64.NO_WRAP)
        val payload = """{"type":"frame","data":"$base64"}"""
        webSocket?.send(payload)
    }

    fun disconnect() {
        webSocket?.close(1000, "User closed")
        client.dispatcher.executorService.shutdown()
    }
}