# הרצת בדיקות Integration ל-TauSync Android

## דרכים להרצת הבדיקות:

### אופציה 1: דרך Android Studio (מומלץ)

**⚠️ חשוב:** Android Studio לא יכול להריץ בדיקות integration עם `main()` דרך Gradle. השתמש באחת מהדרכים הבאות:

#### דרך A: הרצה ישירה דרך Terminal ב-Android Studio

1. **פתח את הפרויקט ב-Android Studio**
   - פתח את התיקייה `TauSync/android/tausync-lib`

2. **בנה את הפרויקט**
   - לחץ על `Build > Make Project` (או `Ctrl+F9`)
   - או לחץ על `Build > Rebuild Project`

3. **פתח את ה-Terminal ב-Android Studio** (View > Tool Windows > Terminal)

4. **הרץ את הסקריפט:**
   ```powershell
   .\run_tests_simple.bat
   ```

#### דרך B: הרצה ידנית דרך Terminal

אחרי Build, פתח PowerShell/CMD ונווט לתיקייה:
```powershell
cd "C:\Users\User\Desktop\OneDrive\CS_BA\Third_Year\final_project\Ecosystem---Final-Project\TauSync\android\tausync-lib"
.\run_tests_simple.bat
```

### אופציה 2: דרך Command Line (אחרי Build)

אחרי שבנית את הפרויקט ב-Android Studio:

1. **פתח PowerShell או CMD**
2. **נווט לתיקיית הפרויקט:**
   ```powershell
   cd "C:\Users\User\Desktop\OneDrive\CS_BA\Third_Year\final_project\Ecosystem---Final-Project\TauSync\android\tausync-lib"
   ```

3. **הרץ את הסקריפט:**
   ```powershell
   .\run_tests_simple.bat
   ```

### אופציה 3: הרצה ידנית

אם הפרויקט כבר built:

```powershell
# Compile
javac -cp "build\intermediates\compile_library_classes_jar\debug\bundleLibCompileToJarDebug\classes.jar;." -d "build\test-classes" "src\test\java\com\example\tausync_lib\IntegrationTest.java"

# Run
java -cp "build\test-classes;build\intermediates\compile_library_classes_jar\debug\bundleLibCompileToJarDebug\classes.jar;." com.example.tausync_lib.IntegrationTest
```

## מה הבדיקות בודקות:

1. **testInterruptDuringStream** - בודק interrupts במהלך streaming (full-duplex)
2. **testStandardFlow** - בודק handshake + streaming
3. **testConcurrentInterrupts** - בודק מספר interrupts במהלך transfer

## פתרון בעיות:

### שגיאת "classes.jar not found"
- פתח את הפרויקט ב-Android Studio
- בנה את הפרויקט (`Build > Make Project`)
- נסה שוב

### שגיאת קומפילציה
- ודא שהפרויקט built בהצלחה ב-Android Studio
- ודא שיש לך JDK 11+ מותקן
- אם יש שגיאות של "cannot find symbol", נסה:
  1. `Build > Clean Project`
  2. `Build > Rebuild Project`
  3. נסה שוב

### שגיאת "SourceSet with name 'unitTest' not found"
- **זו שגיאה של Android Studio** - הוא מנסה להריץ דרך Gradle
- **פתרון:** השתמש ב-`run_tests_simple.bat` במקום להריץ דרך Android Studio
- או הרץ ידנית דרך Terminal (ראה "אופציה 3")

### שגיאת הרצה
- ודא שהפורט 8888 (או 8898, 8908) לא תפוס
- סגור תוכניות אחרות שמשתמשות בפורטים האלה
