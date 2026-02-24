package com.example.android;

import android.os.Bundle;
import android.view.View;
import android.widget.Button;
import android.widget.TextView;
import android.widget.Toast;
import androidx.appcompat.app.AppCompatActivity;

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
    }

    private void handleConnection() {
        // כאן בהמשך תבוא הלוגיקה מול בן
        Toast.makeText(this, "Attempting to connect...", Toast.LENGTH_SHORT).show();

        // דוגמה לשינוי סטטוס ויזואלי
        statusText.setText("Connecting...");
        statusDot.setBackgroundResource(R.drawable.green_dot); // צריך ליצור drawable כזה
    }
}