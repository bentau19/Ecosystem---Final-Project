package com.example.android.ui;

import android.content.Intent;
import android.os.Bundle;
import android.view.Window;
import android.view.WindowManager;
import android.widget.Toast;

import androidx.appcompat.app.AppCompatActivity;
import androidx.core.content.ContextCompat;
import androidx.fragment.app.Fragment;
import androidx.lifecycle.ViewModelProvider;

import com.example.android.R;
import com.example.android.ui.fragments.ActionsFragment;
import com.example.android.ui.fragments.ConnectFragment;
import com.example.android.viewmodel.MainViewModel;
import com.google.zxing.integration.android.IntentIntegrator;
import com.google.zxing.integration.android.IntentResult;

public class MainActivity extends AppCompatActivity {

    private MainViewModel viewModel;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        setupStatusBar();
        setContentView(R.layout.activity_main);

        // אתחול ה-ViewModel (שותף לכל הפרגמנטים)
        viewModel = new ViewModelProvider(this).get(MainViewModel.class);

        if (savedInstanceState == null) {
            replaceFragment(new ConnectFragment());
        }
    }

    public void processScannedData(String qrData) {
        // פקודה אחת פשוטה - ה-ViewModel כבר יודע מה לעשות
        boolean success = viewModel.handleConnectionFromQR(this, qrData);

        if (success) {
            // הצלחנו -> עוברים למסך הפעולות
            replaceFragment(new ActionsFragment());
            Toast.makeText(this, "Connected Successfully!", Toast.LENGTH_SHORT).show();
        } else {
            // נכשלנו -> נשארים במסך החיבור ומראים שגיאה
            Toast.makeText(this, "Invalid QR Code. Please try again.", Toast.LENGTH_LONG).show();
            // אין צורך ב-replaceFragment כי אנחנו כבר ב-ConnectFragment
        }
    }

    public void disconnect() {
        // ניווט חזרה למסך החיבור
        replaceFragment(new ConnectFragment());

        // פקודת ניתוק ב-ViewModel
        viewModel.disconnectFromPc();

        Toast.makeText(this, "Disconnected from PC", Toast.LENGTH_SHORT).show();
    }

    // --- פונקציות עזר (UI) ---

    private void replaceFragment(Fragment fragment) {
        getSupportFragmentManager().beginTransaction()
                .setCustomAnimations(android.R.anim.fade_in, android.R.anim.fade_out)
                .replace(R.id.fragment_container, fragment)
                .commitAllowingStateLoss();
    }

    // הפונקציה שהפרגמנט יקרא לה כשהחיבור מתנתק
    public void navigateToConnectScreen() {
        // כאן אנחנו קוראים לפונקציה הגנרית עם פרגמנט החיבור
        replaceFragment(new ConnectFragment());
    }

    private void setupStatusBar() {
        Window window = getWindow();
        window.addFlags(WindowManager.LayoutParams.FLAG_DRAWS_SYSTEM_BAR_BACKGROUNDS);
        window.setStatusBarColor(ContextCompat.getColor(this, R.color.background_main));
    }

    // --- QR Scanner (Zxing) ---

    public void handleConnection() {
        new IntentIntegrator(this)
                .setDesiredBarcodeFormats(IntentIntegrator.QR_CODE)
                .setPrompt("Scan the PC Dashboard QR Code")
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