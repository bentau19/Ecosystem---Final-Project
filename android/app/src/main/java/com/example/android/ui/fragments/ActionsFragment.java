package com.example.android.ui.fragments;

import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
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
    private List<ToolItem> toolList;

    // Placeholder PC name set by ConnectivityService until the real name arrives over TauSync.
    private static final String PC_NAME_PLACEHOLDER = "PC";

    // UI Components
    private TextView deviceNameText, statusText;
    private View statusDot, btnSettings, btnDisconnect;
    private View progressDisconnecting, tvDisconnectingLabel;
    private View statusRow, pcInfoRow;

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

                // While the PC name is still the placeholder, the basic info hasn't arrived
                // over TauSync yet — show a spinner instead of the (meaningless) "PC" header.
                boolean pcInfoLoaded = !PC_NAME_PLACEHOLDER.equals(pc.getPcName());
                pcInfoRow.setVisibility(pcInfoLoaded ? View.GONE : View.VISIBLE);
                statusRow.setVisibility(pcInfoLoaded ? View.VISIBLE : View.GONE);

                deviceNameText.setText(pcInfoLoaded ? pc.getPcName() : "");
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

            // Surface an indeterminate progress bar while the disconnect frame is in flight.
            int progressVisibility = disconnecting ? View.VISIBLE : View.GONE;
            progressDisconnecting.setVisibility(progressVisibility);
            tvDisconnectingLabel.setVisibility(progressVisibility);
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
        progressDisconnecting = view.findViewById(R.id.progressDisconnecting);
        tvDisconnectingLabel = view.findViewById(R.id.tvDisconnectingLabel);
        statusRow = view.findViewById(R.id.statusRow);
        pcInfoRow = view.findViewById(R.id.pcInfoRow);
    }

    /**
     * populates the tool list and initializes the adapter.
     */
    private void setupRecyclerView(View view) {
        toolsRecyclerView = view.findViewById(R.id.toolsRecyclerView);
        toolsRecyclerView.setLayoutManager(new LinearLayoutManager(getContext()));

        toolList = new ArrayList<>();
        toolList.add(new ToolItem("backup", "File Backup", R.drawable.ic_backup));
        toolList.add(new ToolItem("clipboard", "Send Clipboard to PC", R.drawable.ic_clipboard));
        toolList.add(new ToolItem("camera", "Camera Mirror", R.drawable.ic_camera));

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
                    Toast.makeText(getContext(),
                            R.string.backup_already_in_progress,
                            Toast.LENGTH_SHORT).show();
                } else if (getActivity() instanceof MainActivity) {
                    ((MainActivity) getActivity()).navigateToBackup();
                }
                break;
            case "clipboard":
                handleClipboardSend();
                break;
            case "camera":
                if (getActivity() instanceof MainActivity) {
                    ((MainActivity) getActivity()).navigateToWebcam();
                }
                break;
            default:
                Toast.makeText(getContext(), "Executing: " + toolId, Toast.LENGTH_SHORT).show();
                break;
        }
    }

    private void handleClipboardSend() {
        // 1. Read clipboard content before sending
        ClipboardManager cm = (ClipboardManager) requireContext()
                .getSystemService(Context.CLIPBOARD_SERVICE);
        if (cm == null || !cm.hasPrimaryClip()) {
            Toast.makeText(getContext(), "Clipboard is empty", Toast.LENGTH_SHORT).show();
            return;
        }
        ClipData clip = cm.getPrimaryClip();
        if (clip == null || clip.getItemCount() == 0) {
            Toast.makeText(getContext(), "Clipboard is empty", Toast.LENGTH_SHORT).show();
            return;
        }
        CharSequence text = clip.getItemAt(0).getText();
        if (text == null || text.length() == 0) {
            Toast.makeText(getContext(), "Clipboard is empty", Toast.LENGTH_SHORT).show();
            return;
        }

        // 2. Show preview of what's being sent
        String preview = text.length() > 20
                ? text.subSequence(0, 20) + "..."
                : text.toString();
        Toast.makeText(getContext(), "Sent: '" + preview + "'", Toast.LENGTH_SHORT).show();

        // 3. Visual feedback: change button to "Sent!" + checkmark, disable for 2 seconds
        for (int i = 0; i < toolList.size(); i++) {
            if ("clipboard".equals(toolList.get(i).getId())) {
                ToolItem clipItem = toolList.get(i);
                clipItem.setTitle("Sent!");
                clipItem.setIconRes(R.drawable.ic_check);
                clipItem.setEnabled(false);
                toolsAdapter.notifyItemChanged(i);

                final int idx = i;
                new Handler(Looper.getMainLooper()).postDelayed(() -> {
                    if (!isAdded()) return;
                    clipItem.setTitle("Send Clipboard to PC");
                    clipItem.setIconRes(R.drawable.ic_clipboard);
                    clipItem.setEnabled(true);
                    toolsAdapter.notifyItemChanged(idx);
                }, 2000);
                break;
            }
        }

        // 4. Send
        if (getActivity() instanceof MainActivity) {
            ((MainActivity) getActivity()).sendClipboard();
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
