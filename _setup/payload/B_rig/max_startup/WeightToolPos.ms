-- WeightToolPos.ms : Skin "Weight Tool" 창이 화면 밖에 열리면 Max 창이 있는 모니터 안으로 옮긴다.
-- Max 2014는 이 창 위치를 저장하지 않고 Max 창 오른쪽 끝(화면 밖)에 열기 때문.
-- 설치: %LOCALAPPDATA%\Autodesk\3dsMax\2014 - 64bit\<ENU|KOR>\scripts\startup 에 복사.
(
	global WTPos_timer, WTPos_tick
	try (WTPos_timer.Stop(); WTPos_timer.Dispose()) catch ()

	fn WTPos_tick s e = try
	(
		local maxH = windows.getMaxHWND()
		for c in (windows.getChildrenHWND 0) where c[5] == "Weight Tool" and c[4] == "#32770" and (c[6] == maxH or UIAccessor.GetParentWindow c[1] == maxH) do
		(
			local p = windows.getWindowPos c[1]
			local wa = ((dotNetClass "System.Windows.Forms.Screen").FromHandle (dotNetObject "System.IntPtr" maxH)).WorkingArea
			local inside = p.x >= wa.Left and p.y >= wa.Top and (p.x + p.w) <= wa.Right and (p.y + p.h) <= wa.Bottom
			if not inside do
			(
				local x = wa.Right - p.w - 20
				local y = amax wa.Top (amin p.y (wa.Bottom - p.h))
				windows.setWindowPos c[1] x y p.w p.h true
			)
		)
	) catch ()

	WTPos_timer = dotNetObject "System.Windows.Forms.Timer"
	WTPos_timer.Interval = 1000
	dotNet.addEventHandler WTPos_timer "Tick" WTPos_tick
	WTPos_timer.Start()
)
