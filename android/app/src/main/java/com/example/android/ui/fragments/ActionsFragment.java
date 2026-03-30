package com.example.android.ui.fragments;

import android.os.Bundle;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.TextView;
import android.widget.Toast;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;
import androidx.cardview.widget.CardView; // ייבוא חדש וחשוב!
import androidx.fragment.app.Fragment;

import com.example.android.R;
import com.example.android.ui.MainActivity;

public class ActionsFragment extends Fragment {
    private String deviceName;

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
        if (getArguments() != null) {
            deviceName = getArguments().getString("device_name");
        }
    }

    @Override
    public View onCreateView(@NonNull LayoutInflater inflater, ViewGroup container, Bundle savedInstanceState) {
        // טעינת ה-XML המעודכן עם ה-Cards והצבעים הכהים
        View view = inflater.inflate(R.layout.fragment_actions, container, false);

        // --- עדכון שם המכשיר בסטטוס ---
        TextView deviceNameText = view.findViewById(R.id.deviceNameText);
        if (deviceName != null && !deviceName.isEmpty()) {
            deviceNameText.setText("— " + deviceName);
        }

        // --- הגדרת ה-CardViews (במקום Buttons) ---

        CardView cardBackup = view.findViewById(R.id.cardBackup);
        cardBackup.setOnClickListener(v -> {
            Toast.makeText(getContext(), "Starting File Transfer...", Toast.LENGTH_SHORT).show();
            // כאן תבוא הלוגיקה של שליחת קבצים למחשב
        });

        CardView cardCamera = view.findViewById(R.id.cardCamera);
        cardCamera.setOnClickListener(v -> {
            Toast.makeText(getContext(), "Opening Camera Mirror...", Toast.LENGTH_SHORT).show();
        });

        CardView cardAntivirus = view.findViewById(R.id.cardAntivirus);
        cardAntivirus.setOnClickListener(v -> {
            Toast.makeText(getContext(), "Scanning with PC Antivirus...", Toast.LENGTH_SHORT).show();
        });

        CardView cardSettings = view.findViewById(R.id.cardSettings);
        cardSettings.setOnClickListener(v -> {
            Toast.makeText(getContext(), "Opening Settings...", Toast.LENGTH_SHORT).show();
        });

        // --- כפתור הניתוק (נשאר Button רגיל ב-XML שלנו) ---
        Button btnDisconnect = view.findViewById(R.id.btnDisconnect);
        btnDisconnect.setOnClickListener(v -> {
            if (getActivity() instanceof MainActivity) {
                ((MainActivity) getActivity()).disconnect();
            }
        });

        return view;
    }
}