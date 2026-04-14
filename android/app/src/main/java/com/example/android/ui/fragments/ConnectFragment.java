package com.example.android.ui.fragments;

import android.os.Bundle;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.TextView;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;
import androidx.fragment.app.Fragment;
import androidx.lifecycle.ViewModelProvider;

import com.example.android.R;
import com.example.android.ui.MainActivity;
import com.example.android.viewmodel.MainViewModel;

/**
 * Fragment responsible for the initial connection setup.
 * Displays the local device's IP address and provides an entry point to scan for PCs.
 */
public class ConnectFragment extends Fragment {

    private MainViewModel viewModel;

    @Override
    public View onCreateView(@NonNull LayoutInflater inflater, ViewGroup container, Bundle savedInstanceState) {
        return inflater.inflate(R.layout.fragment_connect, container, false);
    }

    @Override
    public void onViewCreated(@NonNull View view, @Nullable Bundle savedInstanceState) {
        super.onViewCreated(view, savedInstanceState);

        // 1. Bind to the shared ViewModel (scoped to the Activity for synchronization)
        viewModel = new ViewModelProvider(requireActivity()).get(MainViewModel.class);

        // 2. Initialize UI components
        TextView ipDisplayText = view.findViewById(R.id.ipDisplayText);
        Button btnConnect = view.findViewById(R.id.btnConnect);

        // 3. Observer: Monitors changes in the unified ConnectionState
        viewModel.getConnectionState().observe(getViewLifecycleOwner(), state -> {
            if (state != null && state.getLocalDevice() != null && ipDisplayText != null) {
                // ניגשים ל-IP מתוך האובייקט הלוקאלי החדש
                String currentIp = state.getLocalDevice().getIpAddress();
                ipDisplayText.setText("Your IP: " + currentIp);
            }
        });

        // 4. Connection Button: Triggers the PC discovery/scan process in MainActivity
        if (btnConnect != null) {
            btnConnect.setOnClickListener(v -> {
                if (getActivity() instanceof MainActivity) {
                    ((MainActivity) getActivity()).handleConnection();
                }
            });
        }
    }

    /**
     * Utility function to refresh local hardware stats (e.g., IP address).
     */
    private void refreshData() {
        if (viewModel != null && isAdded()) {
            viewModel.refresh();
        }
    }

    @Override
    public void onResume() {
        super.onResume();
        // Refresh local IP whenever the user returns to this screen (e.g., after switching Wi-Fi)
        refreshData();
    }
}