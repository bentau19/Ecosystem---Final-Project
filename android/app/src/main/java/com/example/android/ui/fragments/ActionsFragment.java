package com.example.android.ui.fragments;

import android.os.Bundle;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.TextView;
import android.widget.Toast;

import androidx.annotation.NonNull;
import androidx.fragment.app.Fragment;
import androidx.lifecycle.ViewModelProvider;
import androidx.recyclerview.widget.LinearLayoutManager;
import androidx.recyclerview.widget.RecyclerView;

import com.example.android.R;
import com.example.android.domain.entities.RemoteDeviceInfo;
import com.example.android.domain.enums.ConnectionStatus;
import com.example.android.ui.MainActivity;
import com.example.android.ui.adapters.ToolsAdapter;
import com.example.android.ui.models.ToolItem;
import com.example.android.viewmodel.MainViewModel;

import java.util.ArrayList;
import java.util.List;

/**
 * Fragment responsible for displaying the main actions dashboard once a connection is established.
 * provides access to remote control tools.
 */
public class ActionsFragment extends Fragment {

    private MainViewModel viewModel;
    private ToolsAdapter toolsAdapter;
    private RecyclerView toolsRecyclerView;

    // UI Components
    private TextView deviceNameText, statusText;
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

            android.util.Log.d("ActionsFragment", "ConnectionState changed");

            // --- Update Remote PC Connection State ---
            if (state.isConnected()) {
                RemoteDeviceInfo pc = state.getRemotePC();
                android.util.Log.d("ActionsFragment", "Connected! PC Name: " + pc.getPcName() + ", IP: " + pc.getPcIp());
                deviceNameText.setText(pc.getPcName());
                statusText.setText("Connected via " + pc.getConnectionType() + " (" + pc.getPcIp()+")");
                statusDot.setBackgroundResource(R.drawable.green_dot);
                updateUIState(view, true);
            } else {
                // Handle disconnection: reset UI and navigate back to connection screen
                android.util.Log.d("ActionsFragment", "Disconnected");
                deviceNameText.setText("No Device");
                statusText.setText("Disconnected");
                statusDot.setBackgroundResource(R.drawable.red_dot);
                updateUIState(view, false);

                if (getActivity() instanceof MainActivity) {
                    ((MainActivity) getActivity()).navigateToConnect();
                }
            }
        });

        // 5. Observe ConnectionStatus to disable the disconnect button while a
        //    disconnect is already in flight (prevents double-tap / re-entry).
        viewModel.getConnectionStatus().observe(getViewLifecycleOwner(), status -> {
            if (status == null) return;
            boolean disconnecting = status == ConnectionStatus.DISCONNECTING;
            btnDisconnect.setEnabled(!disconnecting);
            btnDisconnect.setAlpha(disconnecting ? 0.4f : 1.0f);
        });

        // 6. Disconnect Button: Requests termination of the active session
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
     * Routes a tool-card tap to the appropriate sub-screen or action.
     * Add a new {@code case} here as each tool gains its own Fragment/flow.
     */
    private void handleToolClick(String toolId) {
        switch (toolId) {
            case "backup":
                if (viewModel.isBackupActive()) {
                    // A scan or transfer is already running in the background —
                    // block a second one to prevent system overload.
                    Toast.makeText(getContext(),
                            R.string.backup_already_in_progress,
                            Toast.LENGTH_SHORT).show();
                } else if (getActivity() instanceof MainActivity) {
                    ((MainActivity) getActivity()).navigateToBackup();
                }
                break;
            default:
                Toast.makeText(getContext(), "Executing: " + toolId, Toast.LENGTH_SHORT).show();
                break;
        }
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
