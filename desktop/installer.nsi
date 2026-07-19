; -*- mode: nsis -*-
;
; CodeMonkeys Desktop — NSIS installer script.
;
; Packages the PyInstaller onedir output (dist/CodeMonkeys/) into a single
; setup executable.  Creates Start Menu and Desktop shortcuts, registers
; an uninstaller, and writes version metadata.
;
; Build:  makensis desktop/installer.nsi
; (or use scripts/build-installer.ps1 which handles paths automatically)
;
; Requires:  NSIS 3.x  (https://nsis.sourceforge.io)
;

!define PRODUCT_NAME          "CodeMonkeys Desktop"
!define PRODUCT_VERSION       "0.2.1"
!define PRODUCT_PUBLISHER     "CodeMonkeys"
!define PRODUCT_WEB_SITE      "https://github.com/subtiliorars-sys/CodeMonkeys"
!define PRODUCT_DIR_REGKEY    "Software\Microsoft\Windows\CurrentVersion\App Paths\CodeMonkeys.exe"
!define PRODUCT_UNINST_KEY    "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}"
!define PRODUCT_UNINST_ROOT   "HKLM"

; ---- Compiler & output -----------------------------------------------
SetCompressor lzma

Name "${PRODUCT_NAME}"
OutFile "dist\installers\CodeMonkeys-Desktop-Setup-${PRODUCT_VERSION}.exe"
Caption "${PRODUCT_NAME} ${PRODUCT_VERSION} Setup"

RequestExecutionLevel admin
XPStyle on

; ---- Paths -----------------------------------------------------------
; Expects to be run from the repo root so that dist/CodeMonkeys/ exists.
!define APP_DIR   "dist\CodeMonkeys"
!define ICON_FILE "desktop\codemonkeys.ico"

; ---- Version info ----------------------------------------------------
VIProductVersion  "0.2.1.0"
VIAddVersionKey   "ProductName"      "${PRODUCT_NAME}"
VIAddVersionKey   "ProductVersion"   "${PRODUCT_VERSION}"
VIAddVersionKey   "FileDescription"  "${PRODUCT_NAME} installer"
VIAddVersionKey   "FileVersion"      "${PRODUCT_VERSION}"
VIAddVersionKey   "CompanyName"      "${PRODUCT_PUBLISHER}"
VIAddVersionKey   "LegalCopyright"   "Copyright © ${PRODUCT_PUBLISHER}"
VIAddVersionKey   "Comments"         "Visit ${PRODUCT_WEB_SITE}"

; ---- Modern UI 2 -----------------------------------------------------
!include "MUI2.nsh"

!define MUI_ICON            "${ICON_FILE}"
!define MUI_UNICON          "${ICON_FILE}"
!define MUI_ABORTWARNING
!define MUI_UNABORTWARNING

; ---- Interface settings ----------------------------------------------
InstallDir "$PROGRAMFILES64\CodeMonkeys"
InstallDirRegKey HKLM "${PRODUCT_DIR_REGKEY}" ""

ShowInstDetails  show
ShowUninstDetails show
BrandingText "CodeMonkeys Desktop ${PRODUCT_VERSION}"

; ---- Pages -----------------------------------------------------------
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"

; ---- Sections --------------------------------------------------------

Section "MainApplication" SEC_MAIN
    SetOutPath "$INSTDIR"

    ; Copy entire onedir bundle.
    File /r "${APP_DIR}\*.*"

    ; Write uninstaller.
    WriteUninstaller "$INSTDIR\unins000.exe"

    ; -- Start Menu shortcut -------------------------------------------
    CreateDirectory  "$SMPROGRAMS\CodeMonkeys"
    SetOutPath       "$INSTDIR"
    CreateShortCut   "$SMPROGRAMS\CodeMonkeys\CodeMonkeys Desktop.lnk"    "$INSTDIR\CodeMonkeys.exe" "" "$INSTDIR\CodeMonkeys.exe" 0
    CreateShortCut   "$SMPROGRAMS\CodeMonkeys\Uninstall CodeMonkeys.lnk"  "$INSTDIR\unins000.exe"

    ; -- Desktop shortcut -----------------------------------------------
    CreateShortCut   "$DESKTOP\CodeMonkeys Desktop.lnk"                   "$INSTDIR\CodeMonkeys.exe" "" "$INSTDIR\CodeMonkeys.exe" 0

    ; -- Registry: Add/Remove Programs ----------------------------------
    ; Compute installed size in KB.
    SectionGetSize ${SEC_MAIN} $0
    WriteRegStr   ${PRODUCT_UNINST_ROOT} "${PRODUCT_UNINST_KEY}" "DisplayName"       "${PRODUCT_NAME}"
    WriteRegStr   ${PRODUCT_UNINST_ROOT} "${PRODUCT_UNINST_KEY}" "UninstallString"   '"$INSTDIR\unins000.exe"'
    WriteRegStr   ${PRODUCT_UNINST_ROOT} "${PRODUCT_UNINST_KEY}" "DisplayIcon"       "$INSTDIR\CodeMonkeys.exe"
    WriteRegStr   ${PRODUCT_UNINST_ROOT} "${PRODUCT_UNINST_KEY}" "DisplayVersion"    "${PRODUCT_VERSION}"
    WriteRegStr   ${PRODUCT_UNINST_ROOT} "${PRODUCT_UNINST_KEY}" "Publisher"         "${PRODUCT_PUBLISHER}"
    WriteRegStr   ${PRODUCT_UNINST_ROOT} "${PRODUCT_UNINST_KEY}" "URLInfoAbout"      "${PRODUCT_WEB_SITE}"
    WriteRegStr   ${PRODUCT_UNINST_ROOT} "${PRODUCT_UNINST_KEY}" "InstallLocation"   "$INSTDIR"
    WriteRegDword ${PRODUCT_UNINST_ROOT} "${PRODUCT_UNINST_KEY}" "EstimatedSize"     $0
    WriteRegDword ${PRODUCT_UNINST_ROOT} "${PRODUCT_UNINST_KEY}" "NoModify"          1
    WriteRegDword ${PRODUCT_UNINST_ROOT} "${PRODUCT_UNINST_KEY}" "NoRepair"          1

    ; -- Registry: App Paths --------------------------------------------
    WriteRegStr HKLM "${PRODUCT_DIR_REGKEY}" "" "$INSTDIR\CodeMonkeys.exe"
SectionEnd

; ---- Uninstaller -----------------------------------------------------
Section "Uninstall"
    ; Remove shortcuts.
    Delete "$SMPROGRAMS\CodeMonkeys\CodeMonkeys Desktop.lnk"
    Delete "$SMPROGRAMS\CodeMonkeys\Uninstall CodeMonkeys.lnk"
    RMDir  "$SMPROGRAMS\CodeMonkeys"
    Delete "$DESKTOP\CodeMonkeys Desktop.lnk"

    ; Remove app directory and all contents.
    RMDir /r "$INSTDIR"

    ; Remove registry keys.
    DeleteRegKey ${PRODUCT_UNINST_ROOT} "${PRODUCT_UNINST_KEY}"
    DeleteRegKey HKLM "${PRODUCT_DIR_REGKEY}"
SectionEnd
