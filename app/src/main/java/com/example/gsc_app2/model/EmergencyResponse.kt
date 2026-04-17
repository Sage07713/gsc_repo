package com.example.gsc_app2.model



data class EmergencyResponse(
    val type: String,
    val instructions: List<String> = emptyList(),
    val urgencyLevel: String = "LOW",
    val timestamp: Long = System.currentTimeMillis()
)