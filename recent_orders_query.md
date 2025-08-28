# 最近订单查询

## 概述
该查询用于从采购收据数据中获取最近的订单信息，并按日期降序排序，以便轻松查看最新订单。

## 查询参数
- `@LastUpdateDate` - 记录当前执行日期时间
- `@RecentDate` - 设置过滤时间范围（过去3个月）

## 查询结构
```sql
-- 最近的注文と日付を表示するクエリ
-- 作成日: 2025年7月10日

DECLARE @LastUpdateDate smalldatetime = GETDATE()
DECLARE @RecentDate smalldatetime = DATEADD(MONTH, -3, GETDATE()) -- 過去3ヶ月の注文を取得

SELECT TOP 100 -- 最新の100件の注文を取得
          0 as SupplierID
         ,0 as ItemMasterHeaderID
         ,0 as EntityID
         ,'JDEDB' as DBName
         ,PRDOC as ReceiptNumber
         ,cast((PRAREC*0.01) as numeric(19,6))/NULLIF(cast(([PRUREC]*0.0001) as numeric(19,6)),0) as CurrencyAmount
         ,IBBUYR as BuyerPlannerCode
         ,NULL as LaborStandardCost
         ,NULL as MaterialStandardCost
         ,NULL as OverheadStandardCost
         ,cast((ILUNCS*0.0001) as numeric(19,6)) as StandardCost
         ,'USD' as Currency
         ,'False' as CurrencyValue
         ,dateadd(yy,PRRCDJ/1000,0) + PRRCDJ%1000 - 1 as PerformDate
         ,dateadd(yy,PRDGL/1000,0) + PRDGL%1000 - 1 as ReceivedDate
         ,1 as ExchangeRate
         ,PORF.PRUOPN*0.0001 as FSMType
         ,PODF.[PDLITM] as ItemNumber
         ,PODF.[PDITM] as ItemNumberShort
         ,cast((PRPRRC*0.0001) as numeric(19,6)) as Cost
         ,PODF.[PDDCTO] as PurchaseOrderType
         ,cast(([PRLNID]*0.001) as numeric(19,6)) as PurchaseOrderLine
         ,PORF.PRDOCO as PurchaseOrderNumber
         ,cast(([PRUORG]*0.0001) as numeric(19,6)) as OrderQuantity
         ,cast(([PRUREC]*0.0001) as numeric(19,6)) as ReceivedQuantity
         ,PODF.PDUSER as Receiver
         ,'N/A' as RMAtype
         ,Case When ltrim(rtrim([PDMCU])) = '21100' Then '31100'
               When ltrim(rtrim([PDMCU])) = '10800' And left(ltrim(rtrim(Item.[IBGLPT])),1) = 'C' Then '10200'
               When ltrim(rtrim([PDMCU])) = '10800' And left(ltrim(rtrim(Item.[IBGLPT])),1) <> 'C' Then '11400'
               Else ltrim(rtrim([PDMCU])) End as site
         ,PRAN8 as SupplierNumber
         ,CASE
            WHEN IM.IMUOM1 = PODF.PDUOM
              THEN 1
            ELSE cast(isnull(isnull((1/(uom.umconv/10000000)),(uom2.umconv/10000000)), ppf.UCCONV/10000000) as numeric(18,6)) end
            as UOMConversion
         ,PDLNTY as ReceiptType
         ,NULL as PackingSlipNumber
         ,0 as [ReceivedOTDCount]
         ,0 as [ReceivedOTDOnTime]
         ,cast((PRAREC*0.01) as numeric(19,6)) as Spend
         ,isnull(left(ltrim(rtrim(BU_UDC.[DRDL01])),3),NonInvEntity.locationcode) as LocationCode
         ,Case When PDDCTO = 'OT' then 'Y' Else 'N' End as IntraCompanyFlag
         ,PRNLIN POSubLine
         ,PRJELN as JournalEntryLine
         ,PODF.[PDKCOO] as OrderCompany
         ,PODF.[PDDCTO] as ReceivingDocType
         ,PORF.PRSFXO as OrderSuffix
         ,REPLACE(left(Case When ltrim(rtrim(substring(Case When PORF.PRANI = '' Then B.GLANI Else PORF.PRANI End,CHARINDEX('.',Case When PORF.PRANI = '' Then B.GLANI Else PORF.PRANI End,1)+1,15))) is null then ''
              Else ltrim(rtrim(substring(Case When PORF.PRANI = '' Then B.GLANI Else PORF.PRANI End,CHARINDEX('.',Case When PORF.PRANI = '' Then B.GLANI Else PORF.PRANI End,1)+1,15))) End,
              Case When CHARINDEX('.',Case When ltrim(rtrim(substring(Case When PORF.PRANI = '' Then B.GLANI Else PORF.PRANI End,CHARINDEX('.',Case When PORF.PRANI = '' Then B.GLANI Else PORF.PRANI End,1)+1,15))) is null then ''
              Else ltrim(rtrim(substring(Case When PORF.PRANI = '' Then B.GLANI Else PORF.PRANI End,CHARINDEX('.',Case When PORF.PRANI = '' Then B.GLANI Else PORF.PRANI End,1)+1,15))) End,1) = 0 Then 15 
              Else CHARINDEX('.',Case When ltrim(rtrim(substring(Case When PORF.PRANI = '' Then B.GLANI Else PORF.PRANI End,CHARINDEX('.',Case When PORF.PRANI = '' Then B.GLANI Else PORF.PRANI End,1)+1,15))) is null then ''
              Else ltrim(rtrim(substring(Case When PORF.PRANI = '' Then B.GLANI Else PORF.PRANI End,CHARINDEX('.',Case When PORF.PRANI = '' Then B.GLANI Else PORF.PRANI End,1)+1,15))) End,1) End
              ),'.','') as AccrualAccount
         ,PORF.PRLNTY
         ,PORF.PRPTC as VoucherTerms
         ,PORF.PRKCOO as CompanyCode
         ,PORF.PRNXTR StatusCode
         ,dateadd(yy,PORF.PRTRDJ/1000,0) + PORF.PRTRDJ%1000 - 1 as OrderDate
         ,dateadd(yy,PORF.PRDRQJ/1000,0) + PORF.PRDRQJ%1000 - 1 as RequestedDate
         ,PORF.PRUOM as UnitOfMeausre
         ,PORF.PRCRCD as TransCurrency
         ,cast((Case when PORF.PRCRCD='USD' and PORF.PRFREC=0 then (PORF.PRAREC*0.01) else PORF.PRFREC*.01 END) as numeric(19,6)) as SpendTrans
         ,Case when PORF.PRCRCD='USD' then '1' else PORF.PRCRR END as ExchangeRateTrans
         ,Cast((PORF.PRFRRC*0.0001) as numeric(19,6)) as POUnitCostTrans
         ,cast((PRAREC*0.01) as numeric(19,6))/NULLIF(cast(([PRUREC]*0.0001) as numeric(19,6)),0) as POUnitCostLocal
         ,'USD' as LocalCurrency
         ,cast((PRAREC*0.01) as numeric(19,6)) as SpendLocal
         ,@LastUpdateDate as DateLastUpdated
  FROM [PTODS].[JDE].[F43121] PORF
  Left outer Join PTODS.JDE.F4102 as item
              On PORF.PRMCU = item.IBMCU
              And PORF.PRITM = item.IBITM
  Left Outer Join [PTODS].[JDE].[F4311] PODF
              On PODF.PDDOCO = PORF.PRDOCO
              And PODF.PDLNID = PORF.PRLNID
              And PODF.PDMCU = PORF.PRMCU
              And PODF.PDDCTO = PORF.PRDCTO
              And PODF.PDCO = PORF.PRCO
  Left Outer Join [PTODS].[JDE].[F4101] IM
              On PORF.[PRITM] = IM.IMITM
  Left outer join [PTODS].[JDE].F41003 ppf
              on im.IMUOM1=ppf.UCRUM 
              and podf.PdUOM=ppf.UCUM 
  Left Outer Join (Select Receipts.ILMCU,Receipts.[ILITM],Receipts.ILDOCO,Receipts.ILDCTO,Receipts.ILDOC,Receipts.ILDCT,Receipts.ILNLIN,Receipts.ILLNID,AVG(ILUNCS) as ILUNCS
                   From [PTODS].[JDE].[F4111] Receipts
                   Group by Receipts.ILMCU,Receipts.[ILITM],Receipts.ILDOCO,Receipts.ILDCTO,Receipts.ILDOC,Receipts.ILDCT,Receipts.ILNLIN,Receipts.ILLNID)	Receipts
              On PORF.PRMCU = Receipts.ILMCU
              And PORF.PRITM = Receipts.[ILITM]
              And PORF.PRDOCO = Receipts.ILDOCO
              And PORF.PRDCTO = Receipts.ILDCTO
              And PORF.PRDOC = Receipts.ILDOC
              And PORF.PRDCT = Receipts.ILDCT
              And PORF.PRNLIN = Receipts.ILNLIN
              And PORF.PRLNID = Receipts.ILLNID
  Left Outer Join [PTODS].[JDE].[F0005] BU_UDC
              On ltrim(rtrim(BU_UDC.[DRKY])) = ltrim(rtrim(Item.[IBGLPT]))
              And [DRSY] = '61'
  Left Outer Join (Select B.GLDOC,B.GLDCT,B.GLANI, B.GLSUB,B.GLJELN,B.GLLT
                   From [PTODS].[JDE].[F0911] B
                   Group by B.GLDOC,B.GLDCT,B.GLANI, B.GLSUB,B.GLJELN,B.GLLT) B
              On PORF.PRDOC= B.GLDOC 
              and PORF.PRDCT = B.GLDCT 
              and B.GLJELN = 1
              and B.GLLT = 'AA'
  Left join [PTODS].[JDE].[F41002] UOM
              on PORF.[PRITM] = UOM.UMITM
              And IM.IMUOM1 = UOM.UMUM
              And PODF.PDUOM = UOM.UMRUM	  
  Left join [PTODS].[JDE].[F41002] UOM2
              on PORF.[PRITM] = UOM2.UMITM
              And IM.IMUOM1 = UOM2.UMRUM
              And PODF.PDUOM = UOM2.UMUM	 
  Left join (select distinct tm1entity,sitecode,locationcode FROM wqsdw.wqs.platforms 
             where dbname = 'jdedb' and primarysiteflag = 'y') as NonInvEntity  
             on Noninventity.sitecode = 
                Case When ltrim(rtrim([PDMCU])) = '21100' Then '31100'
                     Else ltrim(rtrim([PDMCU])) end
  Where PORF.PRDCT = 'OV'
    and PORF.PRMATC = '1'
    -- 日付条件を最近の期間に変更（過去3ヶ月）
    And dateadd(yy,PRDGL/1000,0) + PRDGL%1000 - 1 >= @RecentDate
    and ltrim(rtrim([PDMCU])) <> '11700'
  -- 最新の注文が先に表示されるように日付で降順にソート
  ORDER BY dateadd(yy,PRDGL/1000,0) + PRDGL%1000 - 1 DESC
```

## 主要功能
1. 过滤最近3个月的订单数据
2. 限制返回前100条记录
3. 按接收日期降序排序，使最新订单优先显示
4. 包含详细的订单信息，如订单号、接收日期、成本、数量等

## 使用说明
此查询适用于监控最近的采购订单活动，特别是在需要快速查看最新交易时非常有用。可以通过调整以下参数来自定义查询：

1. `TOP 100` - 更改此值以获取更多或更少的记录
2. `@RecentDate` - 修改 `DATEADD(MONTH, -3, GETDATE())` 中的月数以调整时间范围

## 注意事项
- 查询针对JDE数据库进行优化
- 默认使用USD作为货币单位
- 查询包含多个JOIN以获取完整的订单信息