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

        // הגדרות תצוגה (סטטוס בר)
        setupStatusBar();
        setContentView(R.layout.activity_main);

        // אתחול ה-ViewModel
        viewModel = new ViewModelProvider(this).get(MainViewModel.class);

        // טעינת המסך הראשון
        if (savedInstanceState == null) {
            replaceFragment(new ConnectFragment());
        }
    }

    // --- לוגיקת החיבור ---

    public void processScannedData(String qrData) {
        // 1. ה-Activity רק מביאה את האחוז סוללה הנוכחי
        int battery = getBatteryPercentage();

        // 2. במקום לבנות אובייקט DeviceInfo כאן, אנחנו רק שולחים ל-ViewModel פקודה: "תתחבר"
        // ה-ViewModel יבנה את האובייקט בעצמו בתוך ה-Repository
        viewModel.connectToDevice(qrData, battery);

        // 3. ניווט
        replaceFragment(new ActionsFragment());
    }

    public void disconnect() {
        // ניווט חזרה
        replaceFragment(new ConnectFragment());

        // פקודת ניתוק ל-ViewModel
        viewModel.disconnectFromDevice();

        Toast.makeText(this, "Disconnected from PC", Toast.LENGTH_SHORT).show();
    }

    // --- פונקציות עזר (ניקיון קוד) ---

    private void replaceFragment(Fragment fragment) {
        getSupportFragmentManager().beginTransaction()
                .setCustomAnimations(android.R.anim.fade_in, android.R.anim.fade_out)
                .replace(R.id.fragment_container, fragment)
                .commitAllowingStateLoss();
    }

    private void setupStatusBar() {
        Window window = getWindow();
        window.addFlags(WindowManager.LayoutParams.FLAG_DRAWS_SYSTEM_BAR_BACKGROUNDS);
        window.setStatusBarColor(ContextCompat.getColor(this, R.color.background_main));
    }

    // --- QR Scanner (קוד של ספרייה חיצונית - נשאר כפי שהוא) ---

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

    private int getBatteryPercentage() {
        android.os.BatteryManager bm = (android.os.BatteryManager) getSystemService(BATTERY_SERVICE);
        return bm.getIntProperty(android.os.BatteryManager.BATTERY_PROPERTY_CAPACITY);
    }
}