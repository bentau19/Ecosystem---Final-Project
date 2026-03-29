package com.example.android;

import android.os.Bundle;
import android.util.Log;
import android.widget.Button;
import android.widget.LinearLayout;
import androidx.appcompat.app.AppCompatActivity;

public class TestTausyncActivity extends AppCompatActivity {

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        // יצירת פריסה פשוטה בקוד (במקום קובץ XML)
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);

        Button testButton = new Button(this);
        testButton.setText("Run TauSync Test");

        // כאן קורה ה"קסם" - מה יקרה כשנלחץ
        testButton.setOnClickListener(v -> {
            runMyTestLogic();
        });

        layout.addView(testButton);
        setContentView(layout);
    }

    private void runMyTestLogic() {
        // כאן אתה כותב את מה שאתה רוצה לבדוק
        // במקום print של פייתון, השתמש ב-Logcat:
        Log.d("TauSyncTest", "Starting test logic...");

        // דוגמה: בדיקת חיבור, שליחת פאקט וכו'
    }
}