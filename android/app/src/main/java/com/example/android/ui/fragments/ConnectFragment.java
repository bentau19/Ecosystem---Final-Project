package com.example.android.ui.fragments;

import android.Manifest;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.graphics.drawable.ColorDrawable;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.TextView;

import androidx.activity.result.ActivityResultLauncher;
import androidx.activity.result.contract.ActivityResultContracts;
import androidx.annotation.NonNull;
import androidx.annotation.Nullable;
import androidx.appcompat.app.AlertDialog;
import androidx.core.content.ContextCompat;
import androidx.fragment.app.Fragment;
import androidx.lifecycle.ViewModelProvider;

import com.example.android.R;
import com.example.android.domain.entities.DiscoveredPc;
import com.example.android.domain.enums.ConnectionStatus;
import com.example.android.domain.enums.DiscoveryStatus;
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
    private Button btnConnectBluetooth;
    private TextView waitingText;
    private View progressConnecting;
    private TextView tvConnectingStatus;
    private TextView tvConnectError;

    // Saved device card
    private View savedDeviceCard;
    private TextView tvSavedDeviceName;

    // Guards against the "PC found" dialog re-showing when LiveData re-delivers PC_FOUND
    // (e.g. on rotation) while the dialog is already up.
    private boolean pcFoundDialogShown = false;

    // Runtime Bluetooth permission request (API 31+). Registered in onCreate.
    private ActivityResultLauncher<String[]> btPermissionLauncher;

    @Override
    public void onCreate(@Nullable Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        // Must register before the fragment reaches STARTED, so onCreate (not onViewCreated).
        btPermissionLauncher = registerForActivityResult(
                new ActivityResultContracts.RequestMultiplePermissions(),
                result -> {
                    boolean allGranted = true;
                    for (Boolean granted : result.values()) {
                        if (!Boolean.TRUE.equals(granted)) {
                            allGranted = false;
                            break;
                        }
                    }
                    if (allGranted) {
                        proceedWithBluetoothConnect();
                    } else {
                        showErrorUI("Bluetooth permission is required to find your PC.");
                    }
                });
    }

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
        btnConnectBluetooth = view.findViewById(R.id.btnConnectBluetooth);
        waitingText = view.findViewById(R.id.waitingText);
        progressConnecting = view.findViewById(R.id.progressConnecting);
        tvConnectingStatus = view.findViewById(R.id.tvConnectingStatus);
        tvConnectError = view.findViewById(R.id.tvConnectError);
        savedDeviceCard = view.findViewById(R.id.savedDeviceCard);
        tvSavedDeviceName = view.findViewById(R.id.tvSavedDeviceName);

        view.findViewById(R.id.btnConnectSaved).setOnClickListener(v -> {
            String mac = viewModel.getSavedAddress();
            if (mac != null) startHybridConnection(mac);
        });
        view.findViewById(R.id.btnForgetDevice).setOnClickListener(v -> {
            viewModel.forgetSavedDevice();
            refreshSavedDeviceCard();
        });

        refreshSavedDeviceCard();

        // 3. Observer: Monitors changes in the unified ConnectionState (local IP display)
        viewModel.getConnectionState().observe(getViewLifecycleOwner(), state -> {
            if (state != null && state.getLocalDevice() != null && ipDisplayText != null) {
                String currentIp = state.getLocalDevice().getIpAddress();
                ipDisplayText.setText("Your IP: " + currentIp);
            }
        });

        // 4. Observer: Drives the connection spinner / error UI off the status machine.
        viewModel.getConnectionStatus().observe(getViewLifecycleOwner(), this::renderConnectionStatus);

        // 5. QR Button: Triggers the QR scan process in MainActivity (existing Wi-Fi path)
        if (btnConnect != null) {
            btnConnect.setOnClickListener(v -> {
                if (getActivity() instanceof MainActivity) {
                    ((MainActivity) getActivity()).handleConnection();
                }
            });
        }

        // 6. Bluetooth Button: starts BLE discovery (or reuses a remembered PC)
        if (btnConnectBluetooth != null) {
            btnConnectBluetooth.setOnClickListener(v -> onBluetoothConnectClicked());
        }

        // 7. Observe the discovery/pairing state machine to drive progress, the confirm
        //    dialog, errors, and the hand-off to the hybrid connection.
        viewModel.getDiscoveryStatus().observe(getViewLifecycleOwner(), this::renderDiscoveryStatus);
    }

    // ── Bluetooth discovery flow ─────────────────────────────────────────────

    /** Connect over Bluetooth: ensure runtime permissions, then discover or reuse a saved PC. */
    private void onBluetoothConnectClicked() {
        if (hasBluetoothPermissions()) {
            proceedWithBluetoothConnect();
        } else {
            btPermissionLauncher.launch(requiredBluetoothPermissions());
        }
    }

    /** Reuse a remembered PC if any, otherwise scan for one. Called once permissions are granted. */
    private void proceedWithBluetoothConnect() {
        String saved = viewModel.getSavedAddress();
        if (saved != null) {
            startHybridConnection(saved);
        } else {
            viewModel.startDiscovery();
        }
    }

    /**
     * The Bluetooth permissions that must be granted at runtime before scanning/bonding.
     *
     * <p>API 31+ uses the granular BLUETOOTH_SCAN/CONNECT. On API ≤ 30 those don't exist as runtime
     * permissions — the install-time BLUETOOTH/BLUETOOTH_ADMIN cover the radio, but a BLE <b>scan</b>
     * additionally requires location (ACCESS_FINE_LOCATION), so we request that instead. (minSdk is
     * 29, so the older path is a real device target, not dead code.)
     */
    private static String[] requiredBluetoothPermissions() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            return new String[]{
                    Manifest.permission.BLUETOOTH_SCAN,
                    Manifest.permission.BLUETOOTH_CONNECT
            };
        }
        return new String[]{Manifest.permission.ACCESS_FINE_LOCATION};
    }

    private boolean hasBluetoothPermissions() {
        for (String permission : requiredBluetoothPermissions()) {
            if (ContextCompat.checkSelfPermission(requireContext(), permission)
                    != PackageManager.PERMISSION_GRANTED) {
                return false;
            }
        }
        return true;
    }

    /** Maps the discovery phase to the connect screen's visual state. */
    private void renderDiscoveryStatus(@Nullable DiscoveryStatus status) {
        if (status == null) return;
        switch (status) {
            case SCANNING:
                showConnectingUI("Scanning for PC over Bluetooth...");
                break;
            case PC_FOUND:
                showPcFoundDialog();
                break;
            case PAIRING:
                showConnectingUI("Pairing...");
                break;
            case PAIRED:
                startHybridConnection(viewModel.getPairedMac());
                break;
            case FAILED:
                String reason = viewModel.getDiscoveryError().getValue();
                showErrorUI(reason != null ? reason : getString(R.string.connection_failed_bt_error));
                break;
            case IDLE:
            default:
                break;
        }
    }

    /** Shows the styled "PC found" confirm dialog (custom dark layout); confirms or cancels pairing. */
    private void showPcFoundDialog() {
        if (pcFoundDialogShown) return;
        DiscoveredPc pc = viewModel.getDiscoveredPc().getValue();
        if (pc == null) return;
        pcFoundDialogShown = true;

        View view = LayoutInflater.from(requireContext())
                .inflate(R.layout.dialog_pc_found, null);
        ((TextView) view.findViewById(R.id.dlgPcName)).setText(pc.getName());
        ((TextView) view.findViewById(R.id.dlgPcMac)).setText(pc.getMacAddress());

        AlertDialog dialog = new AlertDialog.Builder(requireContext())
                .setView(view)
                .setOnCancelListener(d -> {
                    pcFoundDialogShown = false;
                    viewModel.cancelDiscovery();
                    showIdleUI();
                })
                .create();
        // Make the window transparent so the layout's rounded card corners show.
        if (dialog.getWindow() != null) {
            dialog.getWindow().setBackgroundDrawable(new ColorDrawable(Color.TRANSPARENT));
        }

        view.findViewById(R.id.dlgConnect).setOnClickListener(v -> {
            pcFoundDialogShown = false;
            dialog.dismiss();
            viewModel.confirmPairing(pc.getMacAddress());
        });
        view.findViewById(R.id.dlgCancel).setOnClickListener(v -> {
            pcFoundDialogShown = false;
            dialog.dismiss();
            viewModel.cancelDiscovery();
            showIdleUI();
        });
        dialog.show();
    }

    /**
     * Hands the bonded PC's MAC to {@link MainActivity} to start the hybrid (Bluetooth + lazy
     * Wi-Fi) session — the Bluetooth counterpart of the QR button delegating to
     * {@code handleConnection()}.
     */
    private void startHybridConnection(@Nullable String macAddress) {
        if (macAddress == null) {
            Log.w("ConnectFragment", "startHybridConnection called with null MAC — ignoring");
            return;
        }
        if (getActivity() instanceof MainActivity) {
            ((MainActivity) getActivity()).startHybridConnection(macAddress);
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

    private void refreshSavedDeviceCard() {
        boolean hasSaved = viewModel.getSavedAddress() != null;
        if (hasSaved && tvSavedDeviceName != null) {
            String name = viewModel.getSavedDeviceName();
            tvSavedDeviceName.setText(name != null ? name : "My PC");
        }
        setVisible(savedDeviceCard, hasSaved);
        setVisible(btnConnectBluetooth, !hasSaved);
    }

    /** Spinner + status label visible; connect buttons and idle hint hidden. */
    private void showConnectingUI(String label) {
        if (tvConnectingStatus != null) tvConnectingStatus.setText(label);
        setVisible(progressConnecting, true);
        setVisible(tvConnectingStatus, true);
        setVisible(tvConnectError, false);
        setVisible(btnConnect, false);
        setVisible(btnConnectBluetooth, false);
        setVisible(savedDeviceCard, false);
        setVisible(waitingText, false);
    }

    /** Error message visible; connect buttons re-enabled so the user can retry. */
    private void showErrorUI(String message) {
        if (tvConnectError != null) tvConnectError.setText(message);
        setVisible(progressConnecting, false);
        setVisible(tvConnectingStatus, false);
        setVisible(tvConnectError, true);
        setVisible(btnConnect, true);
        setVisible(btnConnectBluetooth, true);
        setVisible(waitingText, true);
        refreshSavedDeviceCard();
    }

    /** Default resting state: just the connect buttons and their hint. */
    private void showIdleUI() {
        setVisible(progressConnecting, false);
        setVisible(tvConnectingStatus, false);
        setVisible(tvConnectError, false);
        setVisible(btnConnect, true);
        setVisible(btnConnectBluetooth, true);
        setVisible(waitingText, true);
        refreshSavedDeviceCard();
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
        refreshData();
        refreshSavedDeviceCard();
        // After a manual disconnect the user chose to leave — skip auto-connect this one time.
        if (viewModel.consumeJustDisconnected()) return;
        if (viewModel.consumeJustDisconnectedByPc()) return;
        if (hasBluetoothPermissions()) {
            String saved = viewModel.getSavedAddress();
            if (saved != null) {
                startHybridConnection(saved);
            } else {
                DiscoveryStatus discoveryStatus = viewModel.getDiscoveryStatus().getValue();
                if (discoveryStatus == null || discoveryStatus == DiscoveryStatus.IDLE) {
                    viewModel.startDiscovery();
                }
            }
        }
    }

    @Override
    public void onStop() {
        super.onStop();
        // Cancel the timeout so it cannot fire while the fragment is off-screen
        // (e.g. app backgrounded mid-connect, or navigated to ActionsFragment).
        cancelTimeout();
    }
}
