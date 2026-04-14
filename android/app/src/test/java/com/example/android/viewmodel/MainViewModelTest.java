//package com.example.android.viewmodel;
//
//import androidx.arch.core.executor.testing.InstantTaskExecutorRule;
//
//import com.example.android.data.repositories.DeviceRepository;
//
//import static org.mockito.Mockito.verify;
//
//import org.junit.Before;
//import org.junit.Rule;
//import org.junit.Test;
//import org.junit.runner.RunWith;
//import org.mockito.Mock;
//import org.mockito.junit.MockitoJUnitRunner;
//
//@RunWith(MockitoJUnitRunner.class)
//public class MainViewModelTest {
//
//    @Rule
//    public InstantTaskExecutorRule instantExecutorRule = new InstantTaskExecutorRule();
//
//    @Mock
//    private DeviceRepository mockRepository; // יוצר כפיל של הריפוזיטורי
//
//    private MainViewModel viewModel;
//
//    @Before
//    public void setUp() {
//        // בטסטים של ViewModel, אנחנו "מזריקים" את המוק במקום האמיתי
//        // (זה דורש שה-ViewModel שלך יקבל את ה-Repository בבנאי)
//        viewModel = new MainViewModel(mockRepository);
//    }
//
//    @Test
//    public void disconnectFromPc_callsRepositoryDisconnect() {
//        // Act
//        viewModel.disconnectFromPc();
//
//        // Assert: מוודאים שה-ViewModel באמת קרא לפונקציה בריפוזיטורי
//        verify(mockRepository).disconnect();
//    }
//}
