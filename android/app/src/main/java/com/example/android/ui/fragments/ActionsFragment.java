package com.example.android.ui.fragments;

import android.os.Bundle;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.ImageView;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;

import androidx.annotation.NonNull;
import androidx.fragment.app.Fragment;
import androidx.lifecycle.ViewModelProvider;
import androidx.recyclerview.widget.LinearLayoutManager;
import androidx.recyclerview.widget.RecyclerView;

import com.example.android.R;
import com.example.android.data.models.entities.DeviceStorageStats;
import com.example.android.data.models.entities.LocalDeviceInfo;
import com.example.android.data.models.entities.RemoteDeviceInfo;
import com.example.android.ui.MainActivity;
import com.example.android.ui.adapters.ToolsAdapter;
import com.example.android.ui.models.ToolItem;
import com.example.android.viewmodel.MainViewModel;

import java.util.ArrayList;
import java.util.List;

/**
 * Fragment responsible for displaying the main actions dashboard once a connection is established.
 * Shows local device status (Battery, Storage) and provides access to remote control tools.
 */
public class ActionsFragment extends Fragment {

    private MainViewModel viewModel;
    private ToolsAdapter toolsAdapter;
    private RecyclerView toolsRecyclerView;

    // UI Components
    private TextView deviceNameText, statusText, batteryText, storageText;
    private ProgressBar batteryProgressBar, storageProgressBar;
    private View statusDot, btnSettings, btnDisconnect;

    @Override
    public View onCreateView(@NonNull LayoutInflater inflater, ViewGroup container, Bundle savedInstanceState) {
        View view = inflater.inflate(R.layout.fragment_actions, container, false);

        // 1. Initialize ViewModel with activity scope to share data across fragments
        viewModel = new ViewModelProvider(requireActivity()).get(MainViewModel.class);

        // 2. Initialize UI components and binding
        initViews(view);

        // 3. Set up the tools list RecyclerView
        setupRecyclerView(view);

        // 4. Observe ConnectionState to update UI in real-time
        viewModel.getConnectionState().observe(getViewLifecycleOwner(), state -> {
            if (state == null) return;

            // --- Update Local Device Data ---
            LocalDeviceInfo phone = state.getLocalDevice();

            // Update Battery UI
            batteryText.setText(phone.getBatteryLevel() + "%");
            batteryProgressBar.setProgress(phone.getBatteryLevel());
            batteryProgressBar.setProgressTintList(android.content.res.ColorStateList.valueOf(android.graphics.Color.parseColor("#4ECCA3")));

            // Update Storage UI using marketing rounding logic from ViewModel
//            storageText.setText(phone.getAvailableStorageBytes() > 0 ? "Storage Active" : "No Data");
            DeviceStorageStats storage = viewModel.getStorageStats();
            storageText.setText(storage.getFormattedStatus());
            storageProgressBar.setProgress(storage.getUsagePercentage());
            storageProgressBar.setProgressTintList(android.content.res.ColorStateList.valueOf(android.graphics.Color.parseColor("#4592AF")));

            // --- Update Remote PC Connection State ---
            if (state.isConnected()) {
                RemoteDeviceInfo pc = state.getRemotePC();
                deviceNameText.setText(pc.getPcName());
                statusText.setText("Connected via " + pc.getConnectionType() + " (" + pc.getPcIp()+")");
                statusDot.setBackgroundResource(R.drawable.green_dot);
                updateUIState(view, true);
            } else {
                // Handle disconnection: reset UI and navigate back to connection screen
                deviceNameText.setText("No Device");
                statusText.setText("Disconnected");
                statusDot.setBackgroundResource(R.drawable.red_dot);
                updateUIState(view, false);

                if (getActivity() instanceof MainActivity) {
                    ((MainActivity) getActivity()).navigateToConnect();
                }
            }
            viewModel.startBatteryMonitoring(requireContext());
        });

        // 5. Disconnect Button: Requests termination of the active session
        btnDisconnect.setOnClickListener(v -> {
            if (getActivity() instanceof MainActivity) {
                ((MainActivity) getActivity()).disconnect();
            }
        });

        return view;
    }

    /**
     * Finds and initializes view references from the layout.
     */
    private void initViews(View view) {
        deviceNameText = view.findViewById(R.id.deviceNameText);
        statusText = view.findViewById(R.id.statusText);
        statusDot = view.findViewById(R.id.statusDot);
        btnSettings = view.findViewById(R.id.btnSettings);
        btnDisconnect = view.findViewById(R.id.btnDisconnect);

        // Access nested views within the included card layouts
        View batteryCard = view.findViewById(R.id.batteryCard);
        View storageCard = view.findViewById(R.id.storageCard);

        // Battery Card Components
        batteryText = batteryCard.findViewById(R.id.valueView);
        batteryProgressBar = batteryCard.findViewById(R.id.progressBar);
        ((TextView) batteryCard.findViewById(R.id.labelView)).setText("PHONE BATTERY");
//        ((ImageView) batteryCard.findViewById(R.id.iconView)).setImageResource(R.drawable.ic_battery);

        // Storage Card Components
        storageText = storageCard.findViewById(R.id.valueView);
        storageProgressBar = storageCard.findViewById(R.id.progressBar);
        ((TextView) storageCard.findViewById(R.id.labelView)).setText("PHONE STORAGE");
//        ((ImageView) storageCard.findViewById(R.id.iconView)).setImageResource(R.drawable.ic_storage);

    }

    /**
     * populates the tool list and initializes the adapter.
     */
    private void setupRecyclerView(View view) {
        toolsRecyclerView = view.findViewById(R.id.toolsRecyclerView);
        toolsRecyclerView.setLayoutManager(new LinearLayoutManager(getContext()));

        List<ToolItem> toolList = new ArrayList<>();
        toolList.add(new ToolItem("backup", "File Backup", R.drawable.ic_backup));
        toolList.add(new ToolItem("camera", "Camera Mirror", R.drawable.ic_camera));
        toolList.add(new ToolItem("security", "Antivirus Scan", R.drawable.ic_security));

        toolsAdapter = new ToolsAdapter(toolList, tool -> {
            // Only execute tools if a connection is currently active
            if (viewModel.getConnectionState().getValue() != null &&
                    viewModel.getConnectionState().getValue().isConnected()) {
                handleToolClick(tool.getId());
            } else {
                Toast.makeText(getContext(), "Please connect to PC first", Toast.LENGTH_SHORT).show();
            }
        });

        toolsRecyclerView.setAdapter(toolsAdapter);
    }

    /**
     * Logic for handling specific tool interactions.
     */
    private void handleToolClick(String toolId) {
        Toast.makeText(getContext(), "Executing: " + toolId, Toast.LENGTH_SHORT).show();
    }

    /**
     * Updates the visual state (alpha/enabled) of tools based on connection status.
     */
    private void updateUIState(View view, boolean enabled) {
        float alpha = enabled ? 1.0f : 0.5f;
        if (toolsRecyclerView != null) {
            toolsRecyclerView.setAlpha(alpha);
            toolsRecyclerView.setEnabled(enabled);
        }
        btnSettings.setAlpha(alpha);
        btnSettings.setEnabled(enabled);
    }
}