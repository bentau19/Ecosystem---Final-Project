package com.example.android.ui.fragments;

import android.os.Bundle;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.TextView;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;
import androidx.fragment.app.Fragment;
import androidx.lifecycle.ViewModelProvider;

import com.example.android.R;
import com.example.android.ui.MainActivity;
import com.example.android.viewmodel.MainViewModel;

public class ConnectFragment extends Fragment {

    private MainViewModel viewModel;

    @Override
    public View onCreateView(@NonNull LayoutInflater inflater, ViewGroup container, Bundle savedInstanceState) {
        return inflater.inflate(R.layout.fragment_connect, container, false);
    }

    @Override
    public void onViewCreated(@NonNull View view, @Nullable Bundle savedInstanceState) {
        super.onViewCreated(view, savedInstanceState);

        // 1. חיבור ל-ViewModel המשותף (שימוש ב-requireActivity כדי שזה יהיה אותו מופע של ה-MainActivity)
        viewModel = new ViewModelProvider(requireActivity()).get(MainViewModel.class);

        // 2. הגדרת ה-Views
        TextView ipDisplayText = view.findViewById(R.id.ipDisplayText);
        Button btnConnect = view.findViewById(R.id.btnConnect);

        // 3. ריענון הנתונים הלוקאליים (כולל ה-IP) ברגע שהמסך עולה
        refreshData();

        // 4. Observer: מאזין לשינויים ב-DeviceInfo
        viewModel.getDeviceInfo().observe(getViewLifecycleOwner(), info -> {
            if (info != null && info.getLocalStats() != null && ipDisplayText != null) {
                // שמי לב לשינוי: info.getLocalStats().getLocalIp()
                // אנחנו ניגשים לשכבה הלוקאלית החדשה שיצרנו
                String currentIp = info.getLocalStats().getLocalIp();
                ipDisplayText.setText("Your IP: " + currentIp);
            }
        });

        // 5. כפתור החיבור
        if (btnConnect != null) {
            btnConnect.setOnClickListener(v -> {
                if (getActivity() instanceof MainActivity) {
                    ((MainActivity) getActivity()).handleConnection();
                }
            });
        }
    }

    /**
     * פונקציית עזר לריענון הנתונים
     */
    private void refreshData() {
        if (viewModel != null) {
            // כרגע אנחנו שולחים 0 בסוללה ואחסון כי עוד לא מימשנו את הסורקים שלהם,
            // אבל ה-IP יתעדכן בזכות ה-context
            viewModel.refreshLocalDeviceStats(requireContext(), 0, 0, 0);
        }
    }

    @Override
    public void onResume() {
        super.onResume();
        // בכל פעם שהמשתמש חוזר לאפליקציה (אולי הוא כיבה והדליק WiFi), נרענן
        refreshData();
    }
}