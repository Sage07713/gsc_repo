package com.example.gsc_app2.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import com.example.gsc_app2.data.EmergencyRepository

class EmergencyViewModelFactory(
    private val repository: EmergencyRepository
) : ViewModelProvider.Factory {
    override fun <T : ViewModel> create(modelClass: Class<T>): T {
        if (modelClass.isAssignableFrom(EmergencyViewModel::class.java)) {
            @Suppress("UNCHECKED_CAST")
            return EmergencyViewModel(repository) as T
        }
        throw IllegalArgumentException("Unknown ViewModel class")
    }
}