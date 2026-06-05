package com.example.android.ui;

import android.Manifest;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.Bundle;
import android.util.Log;
import android.view.Window;
import android.view.WindowManager;
import android.widget.Toast;

import androidx.appcompat.app.AlertDialog;
import androidx.appcompat.app.AppCompatActivity;
import androidx.core.app.ActivityCompat;
import androidx.core.content.ContextCompat;
import androidx.fragment.app.Fragment;
import androidx.lifecycle.ViewModelProvider;

import com.example.android.R;
import com.example.android.domain.entities.FileTransferRequest;
import com.example.android.domain.enums.ConnectionStatus;
import com.example.android.domain.enums.FileTransferStatus;
import com.example.android.services.AppNotificationManager;
import com.example.android.ui.fragments.ActionsFragment;
import com.example.android.ui.fragments.ConnectFragment;
import com.example.android.viewmodel.FileTransferViewModel;
import com.example.android.viewmodel.MainViewModel;
import com.example.android.viewmodel.MainViewModelFactory;
import com.google.zxing.integration.android.IntentIntegrator;
import com.google.zxing.integration.android.IntentResult;

import com.example.android.services.ConnectivityService;

/**
 * Main Activity serves as the primary host for fragments and manages the QR scanning process.
 * It handles the navigation logic between connection setup and the actions dashboard.
 */
public class MainActivity extends AppCompatActivity {

    private static final String TAG = "MainActivity";

    private MainViewModel viewModel;
    private FileTransferViewModel fileTransferViewModel;
    private AppNotificationManager appNotificationManager;
    private boolean isAppInForeground = false;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        setupStatusBar();
        setContentView(R.layout.activity_main);

        // 1. Initialize ViewModels
        MainViewModelFactory factory = new MainViewModelFactory(this.getApplication());
        viewModel = new ViewModelProvider(this, factory).get(MainViewModel.class);
        fileTransferViewModel = new ViewModelProvider(this).get(FileTransferViewModel.class);

        // 2. Initialize notification manager
        appNotificationManager = new AppNotificationManager(this);

        // 3. Observe file transfer state
        observeFileTransfer();

        // 4. Smart navigation logic: Check current connection state from the repository.
        if (savedInstanceState == null) {
            if (viewModel.getConnectionStatus().getValue() == ConnectionStatus.CONNECTED) {
                replaceFragment(new ActionsFragment());
            } else {
                replaceFragment(new ConnectFragment());
            }
        }

        // 5. Listen to real-time TCP connection status and handle navigation.
        viewModel.getConnectionStatus().observe(this, status -> {
            if (status == null) return;
            switch (status) {
                case CONNECTING:
                    Toast.makeText(this, "Connecting...", Toast.LENGTH_SHORT).show();
                    break;
                case CONNECTED:
                    navigateToActions();
                    Toast.makeText(this, "Connected!", Toast.LENGTH_SHORT).show();
                    break;
                case FAILED:
                    navigateToConnect();
                    Toast.makeText(this, "Connection failed. Try again.", Toast.LENGTH_LONG).show();
                    break;
            }
        });
    }

    /**
     * Processes raw QR data scanned from the PC client.
     * @param qrData The string content extracted from the QR code.
     */
    public void processScannedData(String qrData) {
        // ViewModel handles the data parsing and updates the Repository.
        boolean success = viewModel.handleQr(qrData);

        if (success) {
            // Check notification permission (Android 13+) before starting service.
            checkNotificationPermission();

            // Start the service.
            startConnectivityService();
        } else {
            Toast.makeText(this, "Invalid QR Code. Please try again.", Toast.LENGTH_LONG).show();
        }
    }

    /**
     * Starts the Foreground Service to maintain the PC connection.
     */
    private void startConnectivityService() {
        String ip = "";
        if (viewModel.getConnectionState().getValue() != null &&
                viewModel.getConnectionState().getValue().getRemotePC() != null) {
            ip = viewModel.getConnectionState().getValue().getRemotePC().getPcIp();
        }

        Intent serviceIntent = new Intent(this, ConnectivityService.class);
        serviceIntent.putExtra("TARGET_IP", ip);

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            ContextCompat.startForegroundService(this, serviceIntent);
        } else {
            startService(serviceIntent);
        }
    }

    /**
     * Request POST_NOTIFICATIONS permission for Android 13+.
     */
    private void checkNotificationPermission() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS)
                    != PackageManager.PERMISSION_GRANTED) {
                ActivityCompat.requestPermissions(this,
                        new String[]{Manifest.permission.POST_NOTIFICATIONS}, 101);
            }
        }
    }

    /**
     * Orchestrates the disconnection sequence.
     * Sends a command to the service to notify the PC and stop itself.
     */
    public void disconnect() {
        Log.d("TauSyncFlow", "Requesting clean disconnect from service...");

        // Send command to service to notify the PC and shut down.
        Intent intent = new Intent(this, ConnectivityService.class);
        intent.setAction("com.example.android.ACTION_SEND_DISCONNECT");
        startService(intent);

        // Update the UI and Repository state.
        viewModel.disconnect();
        navigateToConnect();
        Toast.makeText(this, "Disconnecting...", Toast.LENGTH_SHORT).show();
    }

    // --- Fragment Navigation ---

    /**
     * Navigates to the Actions dashboard if not already there.
     */
    public void navigateToActions() {
        if (!(getSupportFragmentManager().findFragmentById(R.id.fragment_container) instanceof ActionsFragment)) {
            replaceFragment(new ActionsFragment());
        }
    }

    /**
     * Navigates to the Connection setup screen if not already there.
     */
    public void navigateToConnect() {
        if (!(getSupportFragmentManager().findFragmentById(R.id.fragment_container) instanceof ConnectFragment)) {
            replaceFragment(new ConnectFragment());
        }
    }

    /**
     * Helper method to replace the current fragment with a new one.
     * @param fragment The fragment to display.
     */
    private void replaceFragment(Fragment fragment) {
        getSupportFragmentManager().beginTransaction()
                .setCustomAnimations(android.R.anim.fade_in, android.R.anim.fade_out)
                .replace(R.id.fragment_container, fragment)
                .commitAllowingStateLoss();
    }

    // --- Lifecycle ---

    @Override
    protected void onResume() {
        super.onResume();
        isAppInForeground = true;
    }

    @Override
    protected void onPause() {
        super.onPause();
        isAppInForeground = false;
    }

    // --- File Transfer ---

    /**
     * Observes FileTransferViewModel LiveData.
     *
     * PENDING_APPROVAL:
     *   - Foreground → AlertDialog with Accept / Reject buttons
     *   - Background → heads-up notification with action buttons
     *
     * COMPLETED / REJECTED / FAILED:
     *   - Dismiss notification (if shown), display Toast, reset state
     */
    private void observeFileTransfer() {

        // Observe the incoming request — triggers the approval UI
        fileTransferViewModel.getPendingRequest().observe(this, request -> {
            if (request == null) return;

            appNotificationManager.dismissFileTransferNotification();

            if (isAppInForeground) {
                showFileTransferDialog(request);
            } else {
                appNotificationManager.showFileTransferApprovalNotification(
                        request.getFileName(),
                        request.getFormattedSize()
                );
            }
        });

        // Observe status — react to terminal states
        fileTransferViewModel.getTransferStatus().observe(this, status -> {
            if (status == null) return;

            switch (status) {
                case COMPLETED:
                    appNotificationManager.dismissFileTransferNotification();
                    Toast.makeText(this, "File saved to Downloads ✓", Toast.LENGTH_LONG).show();
                    fileTransferViewModel.reset();
                    break;
                case REJECTED:
                    appNotificationManager.dismissFileTransferNotification();
                    fileTransferViewModel.reset();
                    break;
                case FAILED:
                    appNotificationManager.dismissFileTransferNotification();
                    Toast.makeText(this, "File transfer failed.", Toast.LENGTH_LONG).show();
                    fileTransferViewModel.reset();
                    break;
                default:
                    break;
            }
        });
    }

    /**
     * Shows an AlertDialog asking the user to Accept or Reject the incoming file.
     * Used when the app is in the foreground.
     */
    private void showFileTransferDialog(FileTransferRequest request) {
        new AlertDialog.Builder(this)
                .setTitle("Incoming File from PC")
                .setMessage(request.getFileName() + "\n" + request.getFormattedSize())
                .setPositiveButton("Accept", (dialog, which) -> {
                    fileTransferViewModel.acceptTransfer();
                })
                .setNegativeButton("Reject", (dialog, which) -> {
                    fileTransferViewModel.rejectTransfer();
                })
                .setCancelable(false)
                .show();
    }

    // --- UI Configurations ---

    /**
     * Sets the status bar color to match the application theme.
     */
    private void setupStatusBar() {
        Window window = getWindow();
        window.addFlags(WindowManager.LayoutParams.FLAG_DRAWS_SYSTEM_BAR_BACKGROUNDS);
        window.setStatusBarColor(ContextCompat.getColor(this, R.color.background_main));
    }

    // --- QR Scanner (Zxing Integration) ---

    /**
     * Launches the QR code scanner.
     */
    public void handleConnection() {
        new IntentIntegrator(this)
                .setDesiredBarcodeFormats(IntentIntegrator.QR_CODE)
                .setPrompt("Scan SyncApp QR Code")
                .setBeepEnabled(true)
                .setOrientationLocked(true)
                .initiateScan();
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        IntentResult result = IntentIntegrator.parseActivityResult(requestCode, resultCode, data);
        if (result != null && result.getContents() != null) {
            processScannedData(result.getContents());
        } else {
            super.onActivityResult(requestCode, resultCode, data);
        }
    }
}
