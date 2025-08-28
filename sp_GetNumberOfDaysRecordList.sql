-- =============================================
-- Author:		<Ajit Patil>
-- Create date: <7 Jul 2012>
-- Description:	<Get Days Late Record List>
-- =============================================
CREATE PROCEDURE [dbo].[sp_GetNumberOfDaysRecordList]
AS
BEGIN
	-- SET NOCOUNT ON added to prevent extra result sets from
	-- interfering with SELECT statements.
	SET NOCOUNT ON;

    -- Insert statements for procedure here
	SELECT * FROM Map_NumberOfDays WHERE (DeletedFlag=0 or DeletedFlag is null) ORDER BY DaysLate_Key
END