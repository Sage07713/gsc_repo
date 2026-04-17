package com.example.gsc_app2.ui

import android.graphics.Color
import android.os.Bundle
import android.speech.tts.TextToSpeech
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import androidx.fragment.app.Fragment
import androidx.fragment.app.activityViewModels
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.example.gsc_app2.MainActivity
import com.example.gsc_app2.R
import com.example.gsc_app2.databinding.FragmentInstructionBinding
import com.example.gsc_app2.model.EmergencyResponse
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch
import java.util.Locale

class InstructionFragment : Fragment() {

    private var _binding: FragmentInstructionBinding? = null
    private val binding get() = _binding!!

    private val viewModel: EmergencyViewModel by activityViewModels {
        (requireActivity() as MainActivity).viewModelFactory
    }

    private lateinit var tts: TextToSpeech
    private lateinit var instructionAdapter: InstructionAdapter

    override fun onCreateView(
        inflater: LayoutInflater, container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View {
        _binding = FragmentInstructionBinding.inflate(inflater, container, false)
        return binding.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        instructionAdapter = InstructionAdapter()
        binding.instructionsRecycler.layoutManager = LinearLayoutManager(requireContext())
        binding.instructionsRecycler.adapter = instructionAdapter

        // Initialize Text-to-Speech so the app can talk to the user
        tts = TextToSpeech(requireContext()) { status ->
            if (status == TextToSpeech.SUCCESS) {
                tts.language = Locale.US
            }
        }

        viewLifecycleOwner.lifecycleScope.launch {
            viewModel.latestResponse.collectLatest { response ->
                response?.let {
                    updateUI(it)
                    speakInstructions(it)
                }
            }
        }
    }

    private fun updateUI(response: EmergencyResponse) {
        binding.urgencyBanner.text = "Urgency: ${response.urgencyLevel}"
        binding.urgencyBanner.setBackgroundColor(
            when (response.urgencyLevel) {
                "CRITICAL" -> Color.parseColor("#E24B4A")
                "HIGH"     -> Color.parseColor("#EF9F27")
                else       -> Color.parseColor("#1D9E75")
            }
        )
        instructionAdapter.submitList(response.instructions)
    }

    private fun speakInstructions(response: EmergencyResponse) {
        tts.stop()
        response.instructions.forEachIndexed { i, step ->
            tts.speak("Step ${i + 1}: $step", TextToSpeech.QUEUE_ADD, null, "step_$i")
        }
    }

    override fun onDestroyView() {
        tts.stop()
        tts.shutdown()
        super.onDestroyView()
        _binding = null
    }
}

// Simple Adapter for the List
class InstructionAdapter : RecyclerView.Adapter<InstructionAdapter.ViewHolder>() {
    private var items: List<String> = emptyList()

    fun submitList(list: List<String>) {
        items = list
        notifyDataSetChanged()
    }

    class ViewHolder(view: View) : RecyclerView.ViewHolder(view) {
        val stepNumber: TextView = view.findViewById(R.id.step_number)
        val stepText: TextView = view.findViewById(R.id.step_text)
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ViewHolder {
        val view = LayoutInflater.from(parent.context).inflate(R.layout.item_instruction, parent, false)
        return ViewHolder(view)
    }

    override fun onBindViewHolder(holder: ViewHolder, position: Int) {
        holder.stepNumber.text = (position + 1).toString()
        holder.stepText.text = items[position]
    }

    override fun getItemCount() = items.size
}