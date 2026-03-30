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
import com.example.android.ui.viewmodel.MainViewModel;

public class ConnectFragment extends Fragment {

    private MainViewModel viewModel;

    @Override
    public View onCreateView(@NonNull LayoutInflater inflater, ViewGroup container, Bundle savedInstanceState) {
        View view = inflater.inflate(R.layout.fragment_connect, container, false);

        // 1. חיבור ל-ViewModel המשותף
        viewModel = new ViewModelProvider(requireActivity()).get(MainViewModel.class);

        // 2. הגדרת ה-Views (נניח שיש לך TextView ל-IP ב-XML)
        TextView ipDisplayText = view.findViewById(R.id.ipDisplayText);
        Button btnConnect = view.findViewById(R.id.btnConnect);

        // 3. עדכון ה-IP של הטלפון בתוך ה-ViewModel (שימוש בלוגיקה שבן הביא)
        // הערה: כדאי להוסיף את הפונקציה refreshIpAddress ל-ViewModel כפי שדיברנו קודם
        viewModel.refreshIpAddress(requireContext());

        // 4. Observer: ברגע שה-IP מתעדכן, נציג אותו למשתמש
        viewModel.getDeviceInfo().observe(getViewLifecycleOwner(), info -> {
            if (info != null && ipDisplayText != null) {
                // מציגים את ה-IP של המכשיר הנוכחי כדי שבן יוכל לראות אותו
                ipDisplayText.setText("Your IP: " + info.getIpAddress());
            }
        });

        // 5. כפתור החיבור (פתיחת המצלמה)
        btnConnect.setOnClickListener(v -> {
            if (getActivity() instanceof MainActivity) {
                ((MainActivity) getActivity()).handleConnection();
            }
        });

        return view;
    }

    // refresh ip address on resume
    @Override
    public void onResume() {
        super.onResume();
        // בכל פעם שהמסך חוזר להיות פעיל, נרענן את ה-IP
        if (viewModel != null) {
            viewModel.refreshIpAddress(requireContext());
        }
    }
}