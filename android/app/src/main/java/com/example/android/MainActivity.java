package com.example.android;

import android.content.Intent;
import android.os.Bundle;
import android.widget.Toast;

import androidx.appcompat.app.AppCompatActivity;

import com.google.zxing.integration.android.IntentIntegrator;
import com.google.zxing.integration.android.IntentResult;

public class MainActivity extends AppCompatActivity {

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        if (savedInstanceState == null) {
            // טעינת מסך החיבור כברירת מחדל
            getSupportFragmentManager().beginTransaction()
                    .replace(R.id.fragment_container, new ConnectFragment())
                    .commit();
        }
    }

    public void processScannedData(String data) {
        // מעבר למסך הפעולות
        getSupportFragmentManager().beginTransaction()
                .replace(R.id.fragment_container, ActionsFragment.newInstance(data))
                .commitAllowingStateLoss();
    }

    public void disconnect() {
        // חזרה למסך החיבור
        getSupportFragmentManager().beginTransaction()
                .replace(R.id.fragment_container, new ConnectFragment())
                .commitAllowingStateLoss();
    }

    void handleConnection() {

        IntentIntegrator integrator = new IntentIntegrator(this);

        integrator.setDesiredBarcodeFormats(IntentIntegrator.QR_CODE); // רק קודי QR

        integrator.setPrompt("Scan the QR Code on your PC");

        integrator.setCameraId(0); // מצלמה אחורית

        integrator.setBeepEnabled(true);

        integrator.setBarcodeImageEnabled(true);

        integrator.setOrientationLocked(true); // לא יסובב אוטומטית את המצלמה

        integrator.initiateScan();

    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        // פענוח התוצאה שהגיעה מהסורק
        IntentResult result = IntentIntegrator.parseActivityResult(requestCode, resultCode, data);

        if (result != null) {
            if (result.getContents() == null) {
                // המשתמש יצא מהמצלמה בלי לסרוק
                Toast.makeText(this, "Scan Cancelled", Toast.LENGTH_LONG).show();
            } else {
                // הצלחה! כאן אנחנו מקבלים את הטקסט מה-QR
                String scannedData = result.getContents();

                // עכשיו אנחנו קוראים לפונקציה שכבר כתבת שעוברת לפרגמנט הפעולות
                processScannedData(scannedData);

                Toast.makeText(this, "Connected successfully!", Toast.LENGTH_SHORT).show();
            }
        } else {
            super.onActivityResult(requestCode, resultCode, data);
        }
    }

}