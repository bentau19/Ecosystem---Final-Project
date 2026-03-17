package com.example.android;

import android.os.Bundle;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.TextView;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;
import androidx.fragment.app.Fragment;

public class ActionsFragment extends Fragment {
    private String deviceName;

    // פונקציה סטטית ליצירת מופע חדש של הפרגמנט עם נתונים (שם המכשיר שנסרק)
    public static ActionsFragment newInstance(String deviceName) {
        ActionsFragment fragment = new ActionsFragment();
        Bundle args = new Bundle();
        args.putString("device_name", deviceName);
        fragment.setArguments(args);
        return fragment;
    }

    @Override
    public void onCreate(@Nullable Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        // שליפת הנתונים שנשלחו מה-MainActivity (תוצאת הסריקה)
        if (getArguments() != null) {
            deviceName = getArguments().getString("device_name");
        }
    }

    @Override
    public View onCreateView(LayoutInflater inflater, ViewGroup container, Bundle savedInstanceState) {
        // טעינת ה-XML של הפעולות
        View view = inflater.inflate(R.layout.fragment_actions, container, false);

        // --- עדכון שם המכשיר ב-UI ---
        TextView deviceNameText = view.findViewById(R.id.deviceNameText);
        if (deviceName != null && !deviceName.isEmpty()) {
            deviceNameText.setText(deviceName);
        }

        // --- הגדרת כפתור הניתוק (Disconnect) ---
        Button btnDisconnect = view.findViewById(R.id.btnDisconnect);
        btnDisconnect.setOnClickListener(v -> {
            // קריאה לפונקציית הניתוק שנמצאת ב-MainActivity
            if (getActivity() instanceof MainActivity) {
                ((MainActivity) getActivity()).disconnect();
            }
        });

        // כאן תוכלי להוסיף בעתיד את ה-Listeners לשאר הכפתורים:
        // Button btnBackup = view.findViewById(R.id.btnBackup);
        // btnBackup.setOnClickListener(v -> { ... });

        return view;
    }
}