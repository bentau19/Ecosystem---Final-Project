package com.example.android.ui;

import android.content.Intent;
import android.os.Bundle;
import android.view.Window;
import android.view.WindowManager;
import android.widget.Toast;

import androidx.appcompat.app.AppCompatActivity;
import androidx.core.content.ContextCompat;

import com.example.android.R;
import com.example.android.ui.fragments.ActionsFragment;
import com.example.android.ui.fragments.ConnectFragment;
import com.google.zxing.integration.android.IntentIntegrator;
import com.google.zxing.integration.android.IntentResult;

public class MainActivity extends AppCompatActivity {

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        // --- התאמת צבע הסטטוס-בר לעיצוב הכהה ---
        Window window = getWindow();
        window.addFlags(WindowManager.LayoutParams.FLAG_DRAWS_SYSTEM_BAR_BACKGROUNDS);
        window.setStatusBarColor(ContextCompat.getColor(this, R.color.background_main));

        setContentView(R.layout.activity_main);

        if (savedInstanceState == null) {
            // טעינת מסך החיבור כברירת מחדל עם הגנה מקריסה
            getSupportFragmentManager().beginTransaction()
                    .replace(R.id.fragment_container, new ConnectFragment())
                    .commitAllowingStateLoss();
        }
    }

    public void processScannedData(String data) {
        // מעבר למסך הפעולות (Dashboard) עם הנתונים שנסרקו
        getSupportFragmentManager().beginTransaction()
                .setCustomAnimations(android.R.anim.fade_in, android.R.anim.fade_out) // אנימציה חלקה
                .replace(R.id.fragment_container, ActionsFragment.newInstance(data))
                .commitAllowingStateLoss();
    }

    public void disconnect() {
        // חזרה למסך החיבור (Welcome)
        getSupportFragmentManager().beginTransaction()
                .setCustomAnimations(android.R.anim.fade_in, android.R.anim.fade_out) // אנימציה חלקה
                .replace(R.id.fragment_container, new ConnectFragment())
                .commitAllowingStateLoss();

        Toast.makeText(this, "Disconnected from PC", Toast.LENGTH_SHORT).show();
    }

    public void handleConnection() {
        IntentIntegrator integrator = new IntentIntegrator(this);
        integrator.setDesiredBarcodeFormats(IntentIntegrator.QR_CODE);
        integrator.setPrompt("Scan the PC Dashboard QR Code");
        integrator.setCameraId(0);
        integrator.setBeepEnabled(true);
        integrator.setBarcodeImageEnabled(true);
        integrator.setOrientationLocked(true);
        integrator.initiateScan();
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        IntentResult result = IntentIntegrator.parseActivityResult(requestCode, resultCode, data);

        if (result != null) {
            if (result.getContents() == null) {
                Toast.makeText(this, "Scan Cancelled", Toast.LENGTH_LONG).show();
            } else {
                String scannedData = result.getContents();
                processScannedData(scannedData);
                Toast.makeText(this, "Connected successfully!", Toast.LENGTH_SHORT).show();
            }
        } else {
            super.onActivityResult(requestCode, resultCode, data);
        }
    }
}