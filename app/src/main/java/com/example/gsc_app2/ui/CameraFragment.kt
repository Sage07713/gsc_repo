package com.example.gsc_app2.ui
import com.example.gsc_app2.MainActivity
import android.Manifest
import com.example.gsc_app2.ui.InstructionFragment
import android.content.pm.PackageManager
import android.graphics.Color
import android.os.Bundle
import android.util.Size
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import androidx.activity.result.contract.ActivityResultContracts
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy

import androidx.camera.core.Preview
import androidx.camera.core.resolutionselector.ResolutionSelector
import androidx.camera.core.resolutionselector.ResolutionStrategy
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.core.content.ContextCompat
import androidx.core.graphics.toColorInt
import androidx.fragment.app.Fragment
import androidx.fragment.app.activityViewModels
import androidx.lifecycle.lifecycleScope

import com.example.gsc_app2.R
import com.example.gsc_app2.data.WebSocketClient
import com.example.gsc_app2.databinding.FragmentCameraBinding
import com.example.gsc_app2.utils.ImageUtils
import kotlinx.coroutines.launch
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors

class CameraFragment : Fragment() {

    private var _binding: FragmentCameraBinding? = null
    private val binding get() = _binding!!

    private val viewModel: EmergencyViewModel by activityViewModels {
        (requireActivity() as MainActivity).viewModelFactory
    }

    private lateinit var cameraExecutor: ExecutorService
    private val frameThrottleMs = 500L

    private val requestPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (granted) startCamera()
    }

    override fun onCreateView(
        inflater: LayoutInflater, container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View {
        _binding = FragmentCameraBinding.inflate(inflater, container, false)
        return binding.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        cameraExecutor = Executors.newSingleThreadExecutor()

        if (ContextCompat.checkSelfPermission(requireContext(), Manifest.permission.CAMERA)
            == PackageManager.PERMISSION_GRANTED) {
            startCamera()
        } else {
            requestPermissionLauncher.launch(Manifest.permission.CAMERA)
        }

        viewModel.connect()

        viewLifecycleOwner.lifecycleScope.launch {
            viewModel.connectionState.collect { state ->
                binding.connectionBadge.text = state.name
                binding.connectionBadge.setBackgroundColor(
                    when (state) {
                        WebSocketClient.ConnectionState.CONNECTED -> "#1D9E75".toColorInt()
                        WebSocketClient.ConnectionState.ERROR -> "#E24B4A".toColorInt()
                        else -> "#555555".toColorInt()
                    }
                )
            }
        }

        binding.btnGoToInstructions.setOnClickListener {
            parentFragmentManager.beginTransaction()
                .replace(R.id.fragment_container, InstructionFragment())
                .addToBackStack(null)
                .commit()
        }
    }

    private fun startCamera() {
        val cameraProviderFuture = ProcessCameraProvider.getInstance(requireContext())
        cameraProviderFuture.addListener({
            val cameraProvider = cameraProviderFuture.get()

            val preview = Preview.Builder().build().also {
                it.setSurfaceProvider(binding.previewView.surfaceProvider)
            }

            val resolutionSelector = ResolutionSelector.Builder()
                .setResolutionStrategy(
                    ResolutionStrategy(
                        Size(640, 480),
                        ResolutionStrategy.FALLBACK_RULE_CLOSEST_LOWER
                    )
                ).build()

            val imageAnalyzer = ImageAnalysis.Builder()
                .setResolutionSelector(resolutionSelector)
                .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                .build()
                .also { analysis ->
                    analysis.setAnalyzer(cameraExecutor, FrameAnalyzer { jpegBytes ->
                        viewModel.sendFrame(jpegBytes)
                    })
                }

            cameraProvider.unbindAll()
            cameraProvider.bindToLifecycle(
                viewLifecycleOwner,
                CameraSelector.DEFAULT_BACK_CAMERA,
                preview,
                imageAnalyzer
            )
        }, ContextCompat.getMainExecutor(requireContext()))
    }

    inner class FrameAnalyzer(
        private val onFrame: (ByteArray) -> Unit
    ) : ImageAnalysis.Analyzer {
        private var lastSentTime = 0L

        override fun analyze(image: ImageProxy) {
            val now = System.currentTimeMillis()
            if (now - lastSentTime >= frameThrottleMs) {
                lastSentTime = now
                val jpeg = ImageUtils.toJpeg(image)
                onFrame(jpeg)
            }
            image.close()
        }
    }

    override fun onDestroyView() {
        super.onDestroyView()
        cameraExecutor.shutdown()
        viewModel.disconnect()
        _binding = null
    }
}