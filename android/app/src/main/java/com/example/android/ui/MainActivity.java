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
import androidx.fragment.app.FragmentManager;
import androidx.lifecycle.ViewModelProvider;

import com.example.android.R;
import com.example.android.domain.entities.ReceiveFileRequest;
import com.example.android.domain.enums.ConnectionStatus;
import com.example.android.services.AppNotificationManager;
import com.example.android.ui.fragments.ActionsFragment;
import com.example.android.ui.fragments.BackupFragment;
import com.example.android.ui.fragments.SettingsFragment;
import com.example.android.ui.fragments.WebcamFragment;
import com.example.android.ui.fragments.ConnectFragment;
import com.example.android.viewmodel.FileTransferViewModel;
import com.example.android.viewmodel.MainViewModel;
import com.example.android.viewmodel.MainViewModelFactory;
import com.example.android.services.ConnectivityService;
import com.example.android.utils.StoragePermissions;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

/**
 * Main Activity serves as the primary host for fragments.
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
        // 2. Initialize notification manager and ask for the runtime permissions the app needs.
        appNotificationManager = new AppNotificationManager(this);
        requestStartupPermissions();

        // 3. Observe file transfer state (receive)
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
                    break;
                case CONNECTED:
                    navigateToActions();
                    break;
                case DISCONNECTING:
                    break;
                case DISCONNECTED:
                    // Clear the entire back stack synchronously so any intermediate
                    // screen (e.g. BackupFragment) is dismissed before we replace the
                    // container.  popBackStackImmediate is used instead of the async
                    // variant so the container is in a clean state when navigateToConnect()
                    // runs immediately after.
                    //
                    // Safe at cold-start: LiveData defers delivery until onStart(), by
                    // which time ConnectFragment is already in the container and the back
                    // stack is empty — both calls below are no-ops in that case.
                    getSupportFragmentManager()
                            .popBackStackImmediate(null, FragmentManager.POP_BACK_STACK_INCLUSIVE);
                    navigateToConnect();
                    break;
                case FAILED:
                    navigateToConnect();
                    Toast.makeText(this, "Connection failed. Try again.", Toast.LENGTH_LONG).show();
                    break;
                default:
                    break;
            }
        });
    }

    /**
     * Starts a hybrid (Bluetooth) connection to the bonded PC.
     *
     * <p>The Bluetooth sibling of {@link #processScannedData} + {@link #startConnectivityService}:
     * records the device in the repository (so the UI shows the attempt) and starts the foreground
     * service with the MAC, which then runs {@code connectHybrid}. Called by {@code ConnectFragment}
     * once a PC has been bonded over BLE.
     *
     * @param macAddress The bonded PC's Bluetooth MAC address.
     */
    public void startHybridConnection(String macAddress) {
        viewModel.connectHybrid(macAddress);

        Intent serviceIntent = new Intent(this, ConnectivityService.class);
        serviceIntent.putExtra("TARGET_MAC", macAddress);

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            ContextCompat.startForegroundService(this, serviceIntent);
        } else {
            startService(serviceIntent);
        }
    }

    /** Request code for the combined startup permission request. */
    private static final int REQ_STARTUP_PERMISSIONS = 101;

    /**
     * Asks for everything the app needs to do its job: notifications (Android 13+) so transfers and
     * the connection can report progress, and media read access so a backup can scan the user's
     * photos and videos.
     *
     * <p>Requested together in one call, and at startup rather than mid-task: each system dialog
     * pauses this Activity, and a permission asked in the middle of connecting used to resume
     * straight back into a second connection attempt.
     *
     * <p>Only what is actually missing is requested, so a returning user sees nothing. Nothing is
     * blocked on the outcome either — every feature re-checks its own permission when used, and
     * full-filesystem access for backup is still requested by {@code BackupFragment}, which can
     * explain why it needs a settings screen rather than a dialog.
     */
    private void requestStartupPermissions() {
        List<String> missing = new ArrayList<>();
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU
                && ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS)
                != PackageManager.PERMISSION_GRANTED) {
            missing.add(Manifest.permission.POST_NOTIFICATIONS);
        }
        if (!StoragePermissions.areGranted(this)) {
            missing.addAll(Arrays.asList(StoragePermissions.required()));
        }
        if (!missing.isEmpty()) {
            ActivityCompat.requestPermissions(
                    this, missing.toArray(new String[0]), REQ_STARTUP_PERMISSIONS);
        }
    }

    /**
     * Orchestrates the phone-initiated disconnection sequence.
     *
     * <p>Sends {@code ACTION_SEND_DISCONNECT} to the service, which posts
     * {@code DISCONNECTING} immediately and then writes the TauSync frame on a
     * background thread. When the write completes, the service calls
     * {@code stopSelf()} → {@code cleanup()} → {@code deviceRepository.disconnect()},
     * which posts {@code DISCONNECTED} and drives navigation via the LiveData observers.
     *
     * <p>Do NOT call {@code viewModel.disconnect()} here — doing so posts
     * {@code DISCONNECTED} before the frame is sent, causing the UI to navigate away
     * and the transport to be abandoned mid-flight.
     */
    public void sendClipboard() {
        Intent intent = new Intent(this, ConnectivityService.class);
        intent.setAction("com.example.android.ACTION_SEND_CLIPBOARD");
        startService(intent);
    }

    public void disconnect() {
        Log.d("TauSyncFlow", "Requesting clean disconnect from service...");
        Intent intent = new Intent(this, ConnectivityService.class);
        intent.setAction("com.example.android.ACTION_SEND_DISCONNECT");
        startService(intent);
        // Navigation is driven by the service: cleanup() → deviceRepository.disconnect()
        // → DISCONNECTED posted → ActionsFragment observer → navigateToConnect().
    }

    // --- Fragment Navigation ---

    /**
     * Navigates to the Actions dashboard if not already there.
     *
     * Skips navigation when the back stack is non-empty: that means the user
     * is inside a sub-screen (WebcamFragment, BackupFragment, …) that sits on
     * top of ActionsFragment. This prevents LiveData re-delivery on rotation
     * from wiping the sub-screen and jumping back to ActionsFragment.
     */
    public void navigateToActions() {
        FragmentManager fm = getSupportFragmentManager();
        if (fm.getBackStackEntryCount() > 0) return;
        if (fm.findFragmentById(R.id.fragment_container) instanceof ActionsFragment) return;
        replaceFragment(new ActionsFragment());
    }

    /**
     * Navigates to the Backup configuration screen.
     *
     * <p>Uses addToBackStack so the system/in-screen back button pops BackupFragment
     * and returns to ActionsFragment instead of exiting the app.
     * Top-level screens (Connect, Actions) intentionally stay off the back stack.
     */
    public void navigateToBackup() {
        getSupportFragmentManager().beginTransaction()
                .setCustomAnimations(android.R.anim.fade_in, android.R.anim.fade_out)
                .replace(R.id.fragment_container, new BackupFragment())
                .addToBackStack(null)
                .commitAllowingStateLoss();
    }

    /**
     * Navigates to the Webcam viewfinder screen.
     *
     * <p>Uses addToBackStack so the back button returns to ActionsFragment.
     */
    public void navigateToWebcam() {
        getSupportFragmentManager().beginTransaction()
                .setCustomAnimations(android.R.anim.fade_in, android.R.anim.fade_out)
                .replace(R.id.fragment_container, new WebcamFragment())
                .addToBackStack(null)
                .commitAllowingStateLoss();
    }

    /**
     * Navigates to the Settings screen.
     *
     * <p>Uses addToBackStack so the back button returns to ActionsFragment.
     */
    public void navigateToSettings() {
        getSupportFragmentManager().beginTransaction()
                .setCustomAnimations(android.R.anim.fade_in, android.R.anim.fade_out)
                .replace(R.id.fragment_container, new SettingsFragment())
                .addToBackStack(null)
                .commitAllowingStateLoss();
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
     *
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
     * <p>
     * PENDING_APPROVAL:
     * - Foreground → AlertDialog with Accept / Reject buttons
     * - Background → heads-up notification with action buttons
     * <p>
     * COMPLETED / REJECTED / FAILED:
     * - Dismiss notification (if shown), display Toast, reset state
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
                        request.fileName(),
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
    private void showFileTransferDialog(ReceiveFileRequest request) {
        new AlertDialog.Builder(this)
                .setTitle("Incoming File from PC")
                .setMessage(request.fileName() + "\n" + request.getFormattedSize())
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

}
