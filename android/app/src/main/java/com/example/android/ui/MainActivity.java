package com.example.android.ui;

import android.Manifest;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.Bundle;
import android.view.Window;
import android.view.WindowManager;
import android.widget.Toast;

import androidx.appcompat.app.AppCompatActivity;
import androidx.core.app.ActivityCompat;
import androidx.core.content.ContextCompat;
import androidx.fragment.app.Fragment;
import androidx.lifecycle.ViewModelProvider;

import com.example.android.R;
import com.example.android.ui.fragments.ActionsFragment;
import com.example.android.ui.fragments.ConnectFragment;
import com.example.android.viewmodel.MainViewModel;
import com.example.android.viewmodel.MainViewModelFactory; // הייבוא החדש
import com.google.zxing.integration.android.IntentIntegrator;
import com.google.zxing.integration.android.IntentResult;

import com.example.android.services.ConnectivityService;

/**
 * Main Activity serves as the primary host for fragments and manages the QR scanning process.
 * It handles the navigation logic between connection setup and the actions dashboard.
 */
public class MainActivity extends AppCompatActivity {

    private MainViewModel viewModel;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        setupStatusBar();
        setContentView(R.layout.activity_main);

        // 1. Initialize the shared ViewModel using the Factory
        // כאן אנחנו מעבירים את ה-Application ל-Factory כדי שהוא יכין את ה-Repository
        MainViewModelFactory factory = new MainViewModelFactory(this.getApplication());
        viewModel = new ViewModelProvider(this, factory).get(MainViewModel.class);

        // 2. Smart navigation logic: Check current connection state from the repository
        if (savedInstanceState == null) {
            if (viewModel.getConnectionState().getValue() != null &&
                    viewModel.getConnectionState().getValue().isConnected()) {
                replaceFragment(new ActionsFragment());
            } else {
                replaceFragment(new ConnectFragment());
            }
        }
    }

    /**
     * Processes raw QR data scanned from the PC client.
     * @param qrData The string content extracted from the QR code.
     */
    public void processScannedData(String qrData) {
        // ViewModel handles the data parsing and updates the Repository
        boolean success = viewModel.handleQr(qrData);

        if (success) {
            // בדיקת הרשאות נוטיפיקציה (לאנדרואיד 13+) לפני הפעלת הסרוויס
            checkNotificationPermission();

            // הפעלת הסרוויס - כאן הקסם קורה!
            startConnectivityService();

            navigateToActions();
            Toast.makeText(this, "Connected!", Toast.LENGTH_SHORT).show();
        } else {
            Toast.makeText(this, "Invalid QR Code. Please try again.", Toast.LENGTH_LONG).show();
        }
    }

    /**
     * Starts the Foreground Service to maintain the PC connection.
     */
    private void startConnectivityService() {
        Intent serviceIntent = new Intent(this, ConnectivityService.class);
        // אנחנו יכולים להעביר לסרוויס נתונים דרך ה-Intent אם נרצה בעתיד
        // serviceIntent.putExtra("IP_ADDRESS", viewModel.getIp().getValue());

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            ContextCompat.startForegroundService(this, serviceIntent);
        } else {
            startService(serviceIntent);
        }
    }

    /**
     * Request POST_NOTIFICATIONS permission for Android 13+
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
     * Updates the repository and reverts the UI to the connection screen.
     */
    public void disconnect() {
        // עצירת הסרוויס כשמתנתקים
        stopService(new Intent(this, ConnectivityService.class));

        // Switch back to the connection setup screen
        navigateToConnect();

        // Update the state (this will trigger observers across the app)
        viewModel.disconnect();
        Toast.makeText(this, "Disconnected", Toast.LENGTH_SHORT).show();
    }

    // --- Fragment Navigation ---

    public void navigateToActions() {
        if (!(getSupportFragmentManager().findFragmentById(R.id.fragment_container) instanceof ActionsFragment)) {
            replaceFragment(new ActionsFragment());
        }
    }

    public void navigateToConnect() {
        if (!(getSupportFragmentManager().findFragmentById(R.id.fragment_container) instanceof ConnectFragment)) {
            replaceFragment(new ConnectFragment());
        }
    }

    private void replaceFragment(Fragment fragment) {
        getSupportFragmentManager().beginTransaction()
                .setCustomAnimations(android.R.anim.fade_in, android.R.anim.fade_out)
                .replace(R.id.fragment_container, fragment)
                .commitAllowingStateLoss();
    }

    // --- UI Configurations ---

    private void setupStatusBar() {
        Window window = getWindow();
        window.addFlags(WindowManager.LayoutParams.FLAG_DRAWS_SYSTEM_BAR_BACKGROUNDS);
        window.setStatusBarColor(ContextCompat.getColor(this, R.color.background_main));
    }

    // --- QR Scanner (Zxing Integration) ---

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