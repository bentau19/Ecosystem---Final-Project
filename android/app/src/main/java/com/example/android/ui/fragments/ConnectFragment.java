package com.example.android.ui.fragments;

import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
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
import com.example.android.domain.enums.ConnectionStatus;
import com.example.android.ui.MainActivity;
import com.example.android.viewmodel.MainViewModel;

/**
 * Fragment responsible for the initial connection setup.
 * Displays the local device's IP address and provides an entry point to scan for PCs.
 *
 * <p>While a connection attempt is in flight ({@code CONNECTING} / {@code RECONNECTING})
 * an indeterminate spinner replaces the connect button. A UI-layer timeout guards against
 * the spinner hanging forever if the service never delivers a terminal status. Once
 * {@code CONNECTED} arrives, MainActivity swaps to ActionsFragment — the wait for basic PC
 * info is then surfaced on that screen, not here.
 */
public class ConnectFragment extends Fragment {

    /**
     * Safety-valve timeout (ms). The service's own per-attempt timeout is 5s with up to 2
     * retries (~11s worst case), so 12s is a backstop in case FAILED is never delivered.
     */
    private static final long CONNECT_TIMEOUT_MS = 12_000L;

    private MainViewModel viewModel;

    // Connection-progress UI
    private Button btnConnect;
    private TextView waitingText;
    private View progressConnecting;
    private TextView tvConnectingStatus;
    private TextView tvConnectError;

    private final Handler timeoutHandler = new Handler(Looper.getMainLooper());
    private final Runnable timeoutRunnable = this::onConnectTimeout;
    private boolean timeoutArmed = false;

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
        btnConnect = view.findViewById(R.id.btnConnect);
        waitingText = view.findViewById(R.id.waitingText);
        progressConnecting = view.findViewById(R.id.progressConnecting);
        tvConnectingStatus = view.findViewById(R.id.tvConnectingStatus);
        tvConnectError = view.findViewById(R.id.tvConnectError);

        // 3. Observer: Monitors changes in the unified ConnectionState (local IP display)
        viewModel.getConnectionState().observe(getViewLifecycleOwner(), state -> {
            if (state != null && state.getLocalDevice() != null && ipDisplayText != null) {
                String currentIp = state.getLocalDevice().getIpAddress();
                ipDisplayText.setText("Your IP: " + currentIp);
            }
        });

        // 4. Observer: Drives the connection spinner / error UI off the status machine.
        viewModel.getConnectionStatus().observe(getViewLifecycleOwner(), this::renderConnectionStatus);

        // 5. Connection Button: Triggers the PC discovery/scan process in MainActivity
        if (btnConnect != null) {
            btnConnect.setOnClickListener(v -> {
                if (getActivity() instanceof MainActivity) {
                    ((MainActivity) getActivity()).handleConnection();
                }
            });
        }
    }

    /**
     * Translates a {@link ConnectionStatus} into the connect screen's visual state.
     */
    private void renderConnectionStatus(@Nullable ConnectionStatus status) {
        if (status == null) status = ConnectionStatus.DISCONNECTED;

        switch (status) {
            case CONNECTING:
                armTimeout();
                showConnectingUI(getString(R.string.connecting_label));
                break;
            case RECONNECTING:
                // Do not re-arm the timeout across retries — that would let the spinner run
                // indefinitely. Same spinner, different label.
                showConnectingUI(getString(R.string.reconnecting_label));
                break;
            case CONNECTED:
                // MainActivity swaps to ActionsFragment here; just stop our timer.
                cancelTimeout();
                break;
            case FAILED:
                cancelTimeout();
                showErrorUI(getString(R.string.connection_failed_error));
                break;
            case DISCONNECTED:
            default:
                cancelTimeout();
                showIdleUI();
                break;
        }
    }

    /** Spinner + status label visible; connect button and idle hint hidden. */
    private void showConnectingUI(String label) {
        if (tvConnectingStatus != null) tvConnectingStatus.setText(label);
        setVisible(progressConnecting, true);
        setVisible(tvConnectingStatus, true);
        setVisible(tvConnectError, false);
        setVisible(btnConnect, false);
        setVisible(waitingText, false);
    }

    /** Error message visible; connect button re-enabled so the user can retry. */
    private void showErrorUI(String message) {
        if (tvConnectError != null) tvConnectError.setText(message);
        setVisible(progressConnecting, false);
        setVisible(tvConnectingStatus, false);
        setVisible(tvConnectError, true);
        setVisible(btnConnect, true);
        setVisible(waitingText, true);
    }

    /** Default resting state: just the connect button and its hint. */
    private void showIdleUI() {
        setVisible(progressConnecting, false);
        setVisible(tvConnectingStatus, false);
        setVisible(tvConnectError, false);
        setVisible(btnConnect, true);
        setVisible(waitingText, true);
    }

    private static void setVisible(@Nullable View v, boolean visible) {
        if (v != null) v.setVisibility(visible ? View.VISIBLE : View.GONE);
    }

    /** Arms the safety-valve timeout once per connection attempt. */
    private void armTimeout() {
        if (timeoutArmed) return;
        timeoutArmed = true;
        timeoutHandler.postDelayed(timeoutRunnable, CONNECT_TIMEOUT_MS);
    }

    private void cancelTimeout() {
        timeoutArmed = false;
        timeoutHandler.removeCallbacks(timeoutRunnable);
    }

    /** Fired if the connection never reaches a terminal state in time. */
    private void onConnectTimeout() {
        timeoutArmed = false;
        showErrorUI(getString(R.string.connection_timeout_error));
        // Tear down the half-open attempt so the service stops retrying in the background.
        if (getActivity() instanceof MainActivity) {
            ((MainActivity) getActivity()).disconnect();
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

    @Override
    public void onStop() {
        super.onStop();
        // Cancel the timeout so it cannot fire while the fragment is off-screen
        // (e.g. app backgrounded mid-connect, or navigated to ActionsFragment).
        cancelTimeout();
    }
}
