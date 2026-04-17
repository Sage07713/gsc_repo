package com.example.gsc_app2

import android.os.Bundle
import androidx.activity.enableEdgeToEdge
import androidx.appcompat.app.AppCompatActivity
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import com.example.gsc_app2.data.EmergencyRepository
import com.example.gsc_app2.data.WebSocketClient
import com.example.gsc_app2.ui.CameraFragment
import com.example.gsc_app2.ui.EmergencyViewModelFactory

class MainActivity : AppCompatActivity() {

    // 1. YOUR JETSON IP (Make sure this is correct for your local network)
    private val jetsonIp = "ws://192.168.1.100:8765"

    // 2. This creates the shared ViewModel logic for the whole app
    val viewModelFactory by lazy {
        EmergencyViewModelFactory(
            EmergencyRepository(
                WebSocketClient(jetsonIp)
            )
        )
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContentView(R.layout.activity_main)

        // 3. Fix the Insets to use fragment_container instead of 'main'
        val container = findViewById<android.view.View>(R.id.fragment_container)
        ViewCompat.setOnApplyWindowInsetsListener(container) { v, insets ->
            val systemBars = insets.getInsets(WindowInsetsCompat.Type.systemBars())
            v.setPadding(systemBars.left, systemBars.top, systemBars.right, systemBars.bottom)
            insets
        }

        // 4. Start the app on the Camera screen
        if (savedInstanceState == null) {
            supportFragmentManager.beginTransaction()
                .replace(R.id.fragment_container, CameraFragment())
                .commit()
        }
    }
}