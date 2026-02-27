package com.example.android;

import android.content.Intent;
import android.os.Bundle;
import android.view.View;
import android.widget.Button;
import android.widget.TextView;
import android.widget.Toast;
import androidx.annotation.NonNull;
import androidx.appcompat.app.AppCompatActivity;

import com.google.zxing.integration.android.IntentIntegrator;
import com.google.zxing.integration.android.IntentResult;

public class MainActivity extends AppCompatActivity {

    private Button btnConnect;
    private TextView statusText;
    private View statusDot;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        // טעינת העיצוב מה-XML
        setContentView(R.layout.activity_main);

        // אתחול האלמנטים
        btnConnect = findViewById(R.id.btnConnect);
        statusText = findViewById(R.id.statusText);
        statusDot = findViewById(R.id.statusDot);

        // הגדרת לחיצה על הכפתור
        btnConnect.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                handleConnection();
            }
        });

        if (savedInstanceState != null) {
            boolean isConnected = savedInstanceState.getBoolean("isConnected");
            if (isConnected) {
                String name = savedInstanceState.getString("deviceName");
                processScannedData(name); // הפונקציה שלך כבר יודעת לעדכן את ה-UI
            }
        }
    }

    @Override
    protected void onSaveInstanceState(Bundle outState) {
        super.onSaveInstanceState(outState);
        // נשמור משתנה בוליאני שאומר אם אנחנו מחוברים
        outState.putBoolean("isConnected", findViewById(R.id.actionButtonsContainer).getVisibility() == View.VISIBLE);
        outState.putString("deviceName", ((TextView)findViewById(R.id.deviceNameText)).getText().toString());
    }

    private void handleConnection() {
        IntentIntegrator integrator = new IntentIntegrator(this);
        integrator.setDesiredBarcodeFormats(IntentIntegrator.QR_CODE); // רק קודי QR
        integrator.setPrompt("Scan the QR Code on your PC");
        integrator.setCameraId(0);  // מצלמה אחורית
        integrator.setBeepEnabled(true);
        integrator.setBarcodeImageEnabled(true);
        integrator.setOrientationLocked(true); // לא יסובב אוטומטית את המצלמה
        integrator.initiateScan();
    }

    // הפונקציה שמקבלת את התוצאה אחרי הסריקה
    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        IntentResult result = IntentIntegrator.parseActivityResult(requestCode, resultCode, data);
        if(result != null) {
            if(result.getContents() == null) {
                Toast.makeText(this, "Cancelled", Toast.LENGTH_LONG).show();
            } else {
                // כאן קיבלת את התוכן של הברקוד!
                String scannedData = result.getContents();
                processScannedData(scannedData);
            }
        } else {
            super.onActivityResult(requestCode, resultCode, data);
        }
    }

    private void processScannedData(String data) {
        // עדכון ה-UI לסטטוס מחובר
        statusText.setText("Connecting to PC");
        statusDot.setBackgroundResource(R.drawable.green_dot);
        // הסתרת כפתור החיבור
        findViewById(R.id.initialConnectContainer).setVisibility(View.GONE);
        // הצגת כפתורי הפעולה
        findViewById(R.id.actionButtonsContainer).setVisibility(View.VISIBLE);
        // עדכון שם המכשיר (אם הנתונים הגיעו מהסריקה)
        TextView deviceName = findViewById(R.id.deviceNameText);
        deviceName.setText(data);
        deviceName.setVisibility(View.VISIBLE);

        // --- כאן נגדיר מה קורה בלחיצה על Disconnect ---
        Button btnDisconnect = findViewById(R.id.btnDisconnect);
        btnDisconnect.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                // החזרת המצב לקדמותו (UI)
                findViewById(R.id.actionButtonsContainer).setVisibility(View.GONE);
                deviceName.setVisibility(View.GONE);
                findViewById(R.id.initialConnectContainer).setVisibility(View.VISIBLE);

                statusText.setText("Disconnected");
                statusDot.setBackgroundResource(R.drawable.red_dot);

                // כאן תבוא הפקודה לניתוק הקשר עם המחשב
                // connectionManager.disconnect();

                Toast.makeText(MainActivity.this, "Disconnected", Toast.LENGTH_SHORT).show();
            }
        });

        // כאן תשלחי את ה-IP שנסרק ל-IConnectionManager

        Toast.makeText(this, "Successfully Connected!", Toast.LENGTH_SHORT).show();


    }
}