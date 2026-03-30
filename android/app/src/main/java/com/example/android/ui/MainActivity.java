package com.example.android.ui;

import android.content.Intent;
import android.os.Bundle;
import android.view.Window;
import android.view.WindowManager;
import android.widget.Toast;

import androidx.appcompat.app.AppCompatActivity;
import androidx.core.content.ContextCompat;
import androidx.lifecycle.ViewModelProvider;

import com.example.android.R;
import com.example.android.models.DeviceInfo;
import com.example.android.ui.fragments.ActionsFragment;
import com.example.android.ui.fragments.ConnectFragment;
import com.example.android.ui.viewmodel.MainViewModel;
import com.google.zxing.integration.android.IntentIntegrator;
import com.google.zxing.integration.android.IntentResult;

public class MainActivity extends AppCompatActivity {

    private MainViewModel viewModel;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        // --- התאמת צבע הסטטוס-בר ---
        Window window = getWindow();
        window.addFlags(WindowManager.LayoutParams.FLAG_DRAWS_SYSTEM_BAR_BACKGROUNDS);
        window.setStatusBarColor(ContextCompat.getColor(this, R.color.background_main));

        setContentView(R.layout.activity_main);

        // --- אתחול ה-ViewModel המשותף ---
        viewModel = new ViewModelProvider(this).get(MainViewModel.class);

        if (savedInstanceState == null) {
            getSupportFragmentManager().beginTransaction()
                    .replace(R.id.fragment_container, new ConnectFragment())
                    .commitAllowingStateLoss();
        }
    }

    public void processScannedData(String data) {

        int currentBattery = getBatteryPercentage();

        // 1. יצירת אובייקט נתונים חדש מהסריקה (נניח שהסריקה נתנה לנו את ה-IP של המחשב)
        // לצורך הבדיקה, אנחנו יוצרים DeviceInfo דינמי
        DeviceInfo newConnection = new DeviceInfo(
                "My Galaxy",      // שם הטלפון שלך
                "My PC",       // שם המחשב (כאן אפשר לפענח את ה-data מה-QR)
                data,             // ה-IP שהגיע מהסריקה
                currentBattery,               // אחוז סוללה (בהמשך יגיע מהמערכת)
                "WiFi",           // סוג החיבור
                true              // סטטוס חיבור פעיל
        );

        // 2. עדכון ה-ViewModel - זה יקפיץ אוטומטית את ה-UI בפרגמנטים!
        viewModel.updateDeviceInfo(newConnection);

        // 3. מעבר למסך הפעולות (שימי לב: בלי newInstance!)
        getSupportFragmentManager().beginTransaction()
                .setCustomAnimations(android.R.anim.fade_in, android.R.anim.fade_out)
                .replace(R.id.fragment_container, new ActionsFragment())
                .commitAllowingStateLoss();
    }

    public void disconnect() {
        // 1. קודם כל עוברים למסך החיבור (כדי שהמשתמש לא יראה את הנתונים נעלמים)
        getSupportFragmentManager().beginTransaction()
                .setCustomAnimations(android.R.anim.fade_in, android.R.anim.fade_out)
                .replace(R.id.fragment_container, new ConnectFragment())
                .commitAllowingStateLoss();

        // 2. רק עכשיו מעדכנים את ה-ViewModel.
        // בגלל שעברנו מסך, ה-ActionsFragment כבר לא "מקשיב" (כי הוא הושמד/הוסר)
        DeviceInfo disconnectedInfo = new DeviceInfo(
                "My Galaxy", "None", "0.0.0.0", 0, "None", false
        );
        viewModel.updateDeviceInfo(disconnectedInfo);

        Toast.makeText(this, "Disconnected from PC", Toast.LENGTH_SHORT).show();
    }

    // שאר הפונקציות (handleConnection, onActivityResult) נשארות אותו דבר...
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

    private int getBatteryPercentage() {
        android.os.BatteryManager bm = (android.os.BatteryManager) getSystemService(BATTERY_SERVICE);
        return bm.getIntProperty(android.os.BatteryManager.BATTERY_PROPERTY_CAPACITY);
    }
}