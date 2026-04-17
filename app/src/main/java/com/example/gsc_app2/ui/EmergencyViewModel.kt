package com.example.gsc_app2.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.example.gsc_app2.data.EmergencyRepository
import com.example.gsc_app2.data.WebSocketClient
import com.example.gsc_app2.model.EmergencyResponse
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

class EmergencyViewModel(
    private val repository: EmergencyRepository
) : ViewModel() {

    val connectionState: StateFlow<WebSocketClient.ConnectionState> =
        repository.connectionState

    private val _latestResponse = MutableStateFlow<EmergencyResponse?>(null)
    val latestResponse: StateFlow<EmergencyResponse?> = _latestResponse

    private val _instructionHistory = MutableStateFlow<List<EmergencyResponse>>(emptyList())
    val instructionHistory: StateFlow<List<EmergencyResponse>> = _instructionHistory

    init {
        viewModelScope.launch {
            repository.emergencyInstructions.collect { response ->
                if (response.type == "instruction") {
                    _latestResponse.value = response
                    _instructionHistory.value =
                        (_instructionHistory.value + response).takeLast(20)
                }
            }
        }
    }

    fun connect() = repository.connect()
    fun disconnect() = repository.disconnect()

    fun sendFrame(jpegBytes: ByteArray) {
        viewModelScope.launch(Dispatchers.IO) {
            repository.sendCameraFrame(jpegBytes)
        }
    }
}